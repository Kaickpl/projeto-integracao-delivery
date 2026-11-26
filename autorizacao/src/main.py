from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import secrets
from typing import Literal
from uuid import UUID
import re

import httpx
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWKClientError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, Response

from src.core.database import get_db, settings
from src.modules.papeis import (
    PAPEIS,
    PERMISSAO_GESTAO,
    AuditoriaRbac,
    PapelConta,
    PapelPermissao,
    Permissao,
    PermissaoClienteServico,
)

Papel = Literal["CLIENTE", "LOJA", "ENTREGADOR", "ADMIN"]
PADRAO_PERMISSAO = r"^[a-z_]+:[a-z_]+$"
ATOR_PERFIS = "servico:perfis"

MENSAGEM_TOKEN_INVALIDO = "Token inválido, expirado ou revogado"
MENSAGEM_PERMISSAO_NEGADA = "Permissão negada"
MENSAGEM_RBAC_INDISPONIVEL = "Serviço de Autorização indisponível"


def autenticar(authorization: str | None, segredo: str) -> None:
    valor = authorization.removeprefix("Bearer ") if authorization else ""
    if not segredo or not secrets.compare_digest(valor, segredo):
        raise HTTPException(401, "Credencial de serviço inválida")


def autenticar_perfis(authorization: str | None = Header(default=None)) -> None:
    autenticar(authorization, settings.INTERNAL_SERVICE_TOKEN.get_secret_value())


def autenticar_auth(authorization: str | None = Header(default=None)) -> None:
    autenticar(authorization, settings.AUTHENTICACAO_SERVICE_TOKEN.get_secret_value())


def _erro(status: int, mensagem: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"erro": True, "mensagem": mensagem},
        headers=headers,
    )


class FalhaAutorizacao(Exception):
    """Erro devolvido no formato da turma: {"erro": true, "mensagem": "..."}."""

    def __init__(self, status: int, mensagem: str):
        self.status = status
        self.mensagem = mensagem
        super().__init__(mensagem)


app = FastAPI(title="Serviço de Autorização e RBAC")


@app.exception_handler(FalhaAutorizacao)
async def _tratar_falha_autorizacao(_request: Request, exc: FalhaAutorizacao):
    headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
    return _erro(exc.status, exc.mensagem, headers)


@app.exception_handler(StarletteHTTPException)
async def _tratar_erro_http(_request: Request, exc: StarletteHTTPException):
    return _erro(exc.status_code, str(exc.detail), exc.headers)


@app.exception_handler(RequestValidationError)
async def _tratar_erro_validacao(_request: Request, exc: RequestValidationError):
    partes = []
    for erro in exc.errors():
        campo = ".".join(str(parte) for parte in erro["loc"][1:])
        mensagem = erro["msg"].removeprefix("Value error, ")
        partes.append(f"{campo}: {mensagem}" if campo else mensagem)
    return _erro(422, "; ".join(partes) or "Dados inválidos na requisição")


class PapelEntrada(BaseModel):
    role: str


class TokenValidado(BaseModel):
    ativo: bool
    conta_id: UUID
    role: Papel
    jti: str
    permissoes: list[str]


class ErroValidacao(BaseModel):
    erro: bool
    mensagem: str


class TokenServicoRequest(BaseModel):
    audiencia: str = Field(min_length=1, max_length=500)
    escopos: list[str] = Field(min_length=1, max_length=50)


class TokenServicoValidado(BaseModel):
    ativo: bool
    client_id: str
    audiencia: str
    escopos: list[str]


class VerificacaoRequest(BaseModel):
    permissao: str = Field(max_length=80, pattern=PADRAO_PERMISSAO, examples=["perfis:alterar_status"])


class VerificacaoResponse(BaseModel):
    permitido: bool
    conta_id: UUID
    role: Papel
    permissao: str


class PermissaoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    descricao: str


class PapelPermissoesResponse(BaseModel):
    papel: Papel
    permissoes: list[str]


class PapelContaResponse(BaseModel):
    conta_id: UUID
    role: Papel


class RegistroAuditoria(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ocorrido_em: datetime
    ator: str
    acao: str
    papel: str | None
    permissao: str | None
    conta_id: UUID | None


RESPOSTAS_USUARIO = {
    401: {"model": ErroValidacao, "description": "Token inválido, expirado ou revogado"},
    403: {"model": ErroValidacao, "description": "O papel não tem a permissão necessária"},
    503: {"model": ErroValidacao, "description": "Auth ou PostgreSQL indisponível"},
}


@dataclass(frozen=True)
class Identidade:
    conta_id: UUID
    role: str
    jti: str


# ---------------------------------------------------------------------------
# Identificação do usuário e permissões do papel
# ---------------------------------------------------------------------------


def _identificar_usuario(token: str, db: Session) -> Identidade:
    """Confirma a sessão no Auth e confere o papel atual no RBAC."""
    token = token.strip()
    if not token or len(token) > 8192:
        raise FalhaAutorizacao(401, MENSAGEM_TOKEN_INVALIDO)

    try:
        resposta = httpx.post(
            f"{settings.AUTHENTICACAO_URL.rstrip('/')}/v1/oauth/introspeccao",
            json={"token": token},
            headers={
                "Authorization": (
                    "Bearer "
                    + settings.AUTHENTICACAO_SERVICE_TOKEN.get_secret_value()
                )
            },
            timeout=settings.INTEGRATION_TIMEOUT_SECONDS,
        )
        if resposta.status_code != 200:
            raise FalhaAutorizacao(503, "Serviço de Identidade indisponível")
        dados = resposta.json()
    except (httpx.HTTPError, ValueError):
        raise FalhaAutorizacao(503, "Serviço de Identidade indisponível") from None

    if not isinstance(dados, dict) or dados.get("active") is not True:
        raise FalhaAutorizacao(401, MENSAGEM_TOKEN_INVALIDO)
    try:
        conta_id = UUID(dados["sub"])
        papel = db.get(PapelConta, conta_id)
    except (KeyError, TypeError, ValueError):
        raise FalhaAutorizacao(401, MENSAGEM_TOKEN_INVALIDO) from None
    except SQLAlchemyError:
        raise FalhaAutorizacao(503, MENSAGEM_RBAC_INDISPONIVEL) from None

    # A associação atual no RBAC é autoritativa. Um token emitido antes de
    # remoção ou mudança de papel não mantém a autorização antiga.
    if (
        papel is None
        or dados.get("role") not in PAPEIS
        or papel.role != dados.get("role")
        or not isinstance(dados.get("jti"), str)
    ):
        raise FalhaAutorizacao(401, MENSAGEM_TOKEN_INVALIDO)
    return Identidade(conta_id=conta_id, role=papel.role, jti=dados["jti"])


def _permissoes_do_papel(db: Session, papel: str) -> list[str]:
    """Lê a política atual a cada chamada, sem cache: remoções valem na hora."""
    try:
        return list(
            db.scalars(
                select(PapelPermissao.permissao)
                .where(PapelPermissao.role == papel)
                .order_by(PapelPermissao.permissao)
            ).all()
        )
    except SQLAlchemyError:
        raise FalhaAutorizacao(503, MENSAGEM_RBAC_INDISPONIVEL) from None


esquema_bearer = HTTPBearer(
    auto_error=False,
    description="Access token do usuário emitido pelo Auth",
)


def usuario_autenticado(
    credenciais: HTTPAuthorizationCredentials | None = Depends(esquema_bearer),
    db: Session = Depends(get_db),
) -> Identidade:
    if credenciais is None:
        raise FalhaAutorizacao(401, MENSAGEM_TOKEN_INVALIDO)
    return _identificar_usuario(credenciais.credentials, db)


def exigir_gestor(
    usuario: Identidade = Depends(usuario_autenticado),
    db: Session = Depends(get_db),
) -> Identidade:
    if PERMISSAO_GESTAO not in _permissoes_do_papel(db, usuario.role):
        raise FalhaAutorizacao(403, MENSAGEM_PERMISSAO_NEGADA)
    return usuario


def _auditar(
    db: Session,
    ator: str,
    acao: str,
    *,
    papel: str | None = None,
    permissao: str | None = None,
    conta_id: UUID | None = None,
) -> None:
    db.add(
        AuditoriaRbac(
            ator=ator, acao=acao, papel=papel, permissao=permissao, conta_id=conta_id
        )
    )


# ---------------------------------------------------------------------------
# Validação de tokens e decisão de autorização
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _cliente_jwks(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_jwk_set=True, lifespan=300)


def _decodificar_token_servico(token: str, audiencia: str) -> dict | None:
    cabecalho = jwt.get_unverified_header(token)
    if cabecalho.get("typ") != "at+jwt" or cabecalho.get("alg") != "RS256":
        return None
    jwks_url = f"{settings.AUTHENTICACAO_URL.rstrip('/')}/.well-known/jwks.json"
    chave = _cliente_jwks(jwks_url).get_signing_key_from_jwt(token).key
    claims = jwt.decode(
        token,
        chave,
        algorithms=["RS256"],
        issuer=settings.AUTHENTICACAO_ISSUER,
        audience=audiencia,
        options={"require": ["iss", "sub", "aud", "iat", "exp", "jti", "client_id", "scope"]},
    )
    client_id = claims.get("client_id")
    scopes = claims.get("scope")
    if (
        not isinstance(client_id, str)
        or claims.get("sub") != f"servico:{client_id}"
        or not isinstance(scopes, str)
        or "role" in claims
        or "sid" in claims
    ):
        return None
    escopos = scopes.split()
    if not escopos or any(not re.fullmatch(r"[!-~]+", item) for item in escopos):
        return None
    return {"client_id": client_id, "escopos": escopos}


@app.post(
    "/v1/tokens/servico/validar",
    response_model=TokenServicoValidado,
    tags=["validação"],
    summary="Validar escopos de token de serviço",
    description=(
        "Valida localmente a assinatura RS256 via JWKS, issuer, audiência e expiração; "
        "confere os escopos pedidos com o token e com a política atual do RBAC."
    ),
    responses={
        401: {"model": ErroValidacao, "description": "Token de serviço inválido ou expirado"},
        403: {"model": ErroValidacao, "description": "Escopo não autorizado"},
        503: {"model": ErroValidacao, "description": "JWKS ou PostgreSQL indisponível"},
    },
)
def validar_token_servico(
    dados: TokenServicoRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    esquema, separador, token = (authorization or "").partition(" ")
    if esquema.lower() != "bearer" or not separador or not token.strip():
        return _erro(401, "Token de serviço inválido ou expirado")
    if len(set(dados.escopos)) != len(dados.escopos):
        return _erro(400, "Escopo repetido")
    if any(not re.fullmatch(r"[!-~]+", item) for item in dados.escopos):
        return _erro(400, "Formato de escopo inválido")

    try:
        claims = _decodificar_token_servico(token.strip(), dados.audiencia)
    except (PyJWKClientConnectionError, httpx.HTTPError, OSError):
        return _erro(503, "Chaves públicas da Identidade indisponíveis")
    except (PyJWKClientError, jwt.PyJWTError, ValueError, TypeError):
        return _erro(401, "Token de serviço inválido ou expirado")
    if claims is None:
        return _erro(401, "Token de serviço inválido ou expirado")

    escopos_token = set(claims["escopos"])
    if not set(dados.escopos).issubset(escopos_token):
        return _erro(403, "Escopo não autorizado")
    try:
        escopos_atuais = set(
            db.scalars(
                select(PermissaoClienteServico.escopo).where(
                    PermissaoClienteServico.client_id == claims["client_id"],
                    PermissaoClienteServico.audiencia == dados.audiencia,
                )
            ).all()
        )
    except SQLAlchemyError:
        return _erro(503, MENSAGEM_RBAC_INDISPONIVEL)
    if not set(dados.escopos).issubset(escopos_atuais):
        return _erro(403, "Escopo não autorizado")
    return {
        "ativo": True,
        "client_id": claims["client_id"],
        "audiencia": dados.audiencia,
        "escopos": dados.escopos,
    }


@app.post(
    "/v1/tokens/validar",
    response_model=TokenValidado,
    tags=["validação"],
    summary="Validar token de acesso e obter as permissões do papel",
    description=(
        "Recebe o access token no cabeçalho Bearer, consulta a revogação no Auth, "
        "confirma que o papel continua associado à conta no RBAC e devolve as "
        "permissões atuais desse papel."
    ),
    responses={
        401: {"model": ErroValidacao, "description": "Token inválido, expirado ou revogado"},
        503: {"model": ErroValidacao, "description": "Auth ou PostgreSQL indisponível"},
    },
)
def validar_token(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    esquema, separador, token = (authorization or "").partition(" ")
    if esquema.lower() != "bearer" or not separador:
        raise FalhaAutorizacao(401, MENSAGEM_TOKEN_INVALIDO)
    usuario = _identificar_usuario(token, db)
    return {
        "ativo": True,
        "conta_id": str(usuario.conta_id),
        "role": usuario.role,
        "jti": usuario.jti,
        "permissoes": _permissoes_do_papel(db, usuario.role),
    }


@app.post(
    "/v1/autorizacao/verificar",
    response_model=VerificacaoResponse,
    tags=["validação"],
    summary="Verificar se o usuário pode executar uma ação",
    description=(
        "Valida o access token como em `/v1/tokens/validar` e confere se o papel "
        "atual tem a permissão pedida. A posse do recurso (por exemplo, se a loja "
        "é do usuário) continua sendo conferida pelo serviço dono do recurso."
    ),
    responses=RESPOSTAS_USUARIO,
)
def verificar_permissao(
    dados: VerificacaoRequest,
    usuario: Identidade = Depends(usuario_autenticado),
    db: Session = Depends(get_db),
):
    if dados.permissao not in _permissoes_do_papel(db, usuario.role):
        raise FalhaAutorizacao(403, MENSAGEM_PERMISSAO_NEGADA)
    return {
        "permitido": True,
        "conta_id": str(usuario.conta_id),
        "role": usuario.role,
        "permissao": dados.permissao,
    }


# ---------------------------------------------------------------------------
# Gestão de papéis e permissões (exige rbac:gerenciar)
# ---------------------------------------------------------------------------


@app.get(
    "/v1/permissoes",
    response_model=list[PermissaoResponse],
    tags=["gestão"],
    summary="Listar o catálogo de permissões",
    responses=RESPOSTAS_USUARIO,
)
def listar_permissoes(
    _gestor: Identidade = Depends(exigir_gestor),
    db: Session = Depends(get_db),
):
    try:
        return list(db.scalars(select(Permissao).order_by(Permissao.codigo)).all())
    except SQLAlchemyError:
        raise FalhaAutorizacao(503, MENSAGEM_RBAC_INDISPONIVEL) from None


@app.get(
    "/v1/papeis",
    response_model=list[PapelPermissoesResponse],
    tags=["gestão"],
    summary="Listar os papéis e as permissões de cada um",
    responses=RESPOSTAS_USUARIO,
)
def listar_papeis(
    _gestor: Identidade = Depends(exigir_gestor),
    db: Session = Depends(get_db),
):
    return [
        {"papel": papel, "permissoes": _permissoes_do_papel(db, papel)}
        for papel in PAPEIS
    ]


@app.get(
    "/v1/papeis/{papel}/permissoes",
    response_model=PapelPermissoesResponse,
    tags=["gestão"],
    summary="Listar as permissões de um papel",
    responses=RESPOSTAS_USUARIO,
)
def listar_permissoes_do_papel(
    papel: Papel,
    _gestor: Identidade = Depends(exigir_gestor),
    db: Session = Depends(get_db),
):
    return {"papel": papel, "permissoes": _permissoes_do_papel(db, papel)}


def _exigir_permissao_do_catalogo(db: Session, permissao: str) -> None:
    if db.get(Permissao, permissao) is None:
        raise FalhaAutorizacao(404, "Permissão não encontrada")


@app.put(
    "/v1/papeis/{papel}/permissoes/{permissao}",
    response_model=PapelPermissoesResponse,
    tags=["gestão"],
    summary="Conceder uma permissão a um papel",
    description="Idempotente: conceder uma permissão que o papel já tem não muda nada.",
    responses={
        **RESPOSTAS_USUARIO,
        404: {"model": ErroValidacao, "description": "Permissão fora do catálogo"},
    },
)
def conceder_permissao(
    papel: Papel,
    permissao: str = Path(max_length=80, pattern=PADRAO_PERMISSAO),
    gestor: Identidade = Depends(exigir_gestor),
    db: Session = Depends(get_db),
):
    try:
        _exigir_permissao_do_catalogo(db, permissao)
        concedida = db.execute(
            insert(PapelPermissao)
            .values(role=papel, permissao=permissao)
            .on_conflict_do_nothing()
            .returning(PapelPermissao.permissao)
        ).first()
        if concedida is not None:
            _auditar(
                db,
                str(gestor.conta_id),
                "PERMISSAO_CONCEDIDA",
                papel=papel,
                permissao=permissao,
            )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise FalhaAutorizacao(503, MENSAGEM_RBAC_INDISPONIVEL) from None
    return {"papel": papel, "permissoes": _permissoes_do_papel(db, papel)}


@app.delete(
    "/v1/papeis/{papel}/permissoes/{permissao}",
    response_model=PapelPermissoesResponse,
    tags=["gestão"],
    summary="Remover uma permissão de um papel",
    description=(
        "Idempotente. Vale na próxima requisição, sem esperar o token expirar. "
        "`rbac:gerenciar` não pode ser removida do papel ADMIN."
    ),
    responses={
        **RESPOSTAS_USUARIO,
        404: {"model": ErroValidacao, "description": "Permissão fora do catálogo"},
        409: {"model": ErroValidacao, "description": "Remoção bloquearia a gestão do RBAC"},
    },
)
def remover_permissao(
    papel: Papel,
    permissao: str = Path(max_length=80, pattern=PADRAO_PERMISSAO),
    gestor: Identidade = Depends(exigir_gestor),
    db: Session = Depends(get_db),
):
    if papel == "ADMIN" and permissao == PERMISSAO_GESTAO:
        raise FalhaAutorizacao(
            409, f"A permissão {PERMISSAO_GESTAO} não pode ser removida do papel ADMIN"
        )
    try:
        _exigir_permissao_do_catalogo(db, permissao)
        removida = db.execute(
            delete(PapelPermissao)
            .where(PapelPermissao.role == papel, PapelPermissao.permissao == permissao)
            .returning(PapelPermissao.permissao)
        ).first()
        if removida is not None:
            _auditar(
                db,
                str(gestor.conta_id),
                "PERMISSAO_REMOVIDA",
                papel=papel,
                permissao=permissao,
            )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise FalhaAutorizacao(503, MENSAGEM_RBAC_INDISPONIVEL) from None
    return {"papel": papel, "permissoes": _permissoes_do_papel(db, papel)}


@app.get(
    "/v1/contas/{conta_id}/papel",
    response_model=PapelContaResponse,
    tags=["gestão"],
    summary="Consultar o papel de uma conta",
    responses={
        **RESPOSTAS_USUARIO,
        404: {"model": ErroValidacao, "description": "Conta sem papel associado"},
    },
)
def consultar_papel_gestao(
    conta_id: UUID,
    _gestor: Identidade = Depends(exigir_gestor),
    db: Session = Depends(get_db),
):
    try:
        papel = db.get(PapelConta, conta_id)
    except SQLAlchemyError:
        raise FalhaAutorizacao(503, MENSAGEM_RBAC_INDISPONIVEL) from None
    if papel is None:
        raise FalhaAutorizacao(404, "Papel não associado")
    return {"conta_id": papel.conta_id, "role": papel.role}


@app.get(
    "/v1/auditoria",
    response_model=list[RegistroAuditoria],
    tags=["gestão"],
    summary="Consultar o histórico de mudanças de papéis e permissões",
    description="Mais recentes primeiro. Os filtros podem ser combinados.",
    responses=RESPOSTAS_USUARIO,
)
def listar_auditoria(
    papel: Papel | None = None,
    permissao: str | None = Query(None, max_length=80, pattern=PADRAO_PERMISSAO),
    conta_id: UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    _gestor: Identidade = Depends(exigir_gestor),
    db: Session = Depends(get_db),
):
    consulta = (
        select(AuditoriaRbac)
        .order_by(AuditoriaRbac.ocorrido_em.desc(), AuditoriaRbac.id.desc())
        .offset(skip)
        .limit(limit)
    )
    if papel:
        consulta = consulta.where(AuditoriaRbac.papel == papel)
    if permissao:
        consulta = consulta.where(AuditoriaRbac.permissao == permissao)
    if conta_id:
        consulta = consulta.where(AuditoriaRbac.conta_id == conta_id)
    try:
        return list(db.scalars(consulta).all())
    except SQLAlchemyError:
        raise FalhaAutorizacao(503, MENSAGEM_RBAC_INDISPONIVEL) from None


# ---------------------------------------------------------------------------
# Rotas internas entre serviços
# ---------------------------------------------------------------------------


@app.get("/v1/interno/contas/{conta_id}/papel", tags=["integração interna"])
def consultar_papel(
    conta_id: UUID,
    _auth: None = Depends(autenticar_auth),
    db: Session = Depends(get_db),
):
    papel = db.get(PapelConta, conta_id)
    if papel is None:
        raise HTTPException(404, "Papel não associado")
    return {"conta_id": str(papel.conta_id), "role": papel.role}


@app.get("/v1/interno/clientes/{client_id}/permissoes", tags=["integração interna"])
def consultar_permissoes_cliente_servico(
    client_id: str,
    audiencia: str = Query(min_length=1, max_length=500),
    _auth: None = Depends(autenticar_auth),
    db: Session = Depends(get_db),
):
    permissoes = db.scalars(
        select(PermissaoClienteServico.escopo)
        .where(
            PermissaoClienteServico.client_id == client_id,
            PermissaoClienteServico.audiencia == audiencia,
        )
        .order_by(PermissaoClienteServico.escopo)
    ).all()
    return {
        "client_id": client_id,
        "audiencia": audiencia,
        "escopos": permissoes,
    }


@app.put("/v1/interno/contas/{conta_id}/papel", tags=["integração interna"])
def associar_papel(
    conta_id: UUID,
    dados: PapelEntrada,
    _auth: None = Depends(autenticar_perfis),
    db: Session = Depends(get_db),
):
    if dados.role not in PAPEIS:
        raise HTTPException(400, "Papel inválido")
    comando = insert(PapelConta).values(conta_id=conta_id, role=dados.role)
    alterado = db.execute(
        comando.on_conflict_do_update(
            index_elements=[PapelConta.conta_id],
            set_={"role": comando.excluded.role},
            where=PapelConta.role != comando.excluded.role,
        ).returning(PapelConta.conta_id)
    ).first()
    # Repetições idempotentes do cadastro não geram registros duplicados.
    if alterado is not None:
        _auditar(db, ATOR_PERFIS, "PAPEL_ASSOCIADO", papel=dados.role, conta_id=conta_id)
    db.commit()
    return {"conta_id": str(conta_id), "role": dados.role}


@app.delete(
    "/v1/interno/contas/{conta_id}/papel",
    status_code=204,
    tags=["integração interna"],
    summary="Remover o papel de uma conta",
    description=(
        "Chamada por Perfis antes de apagar um perfil. Idempotente: responde 204 "
        "mesmo que a conta já não tenha papel. Tokens da conta deixam de ser aceitos "
        "na validação online."
    ),
)
def remover_papel(
    conta_id: UUID,
    _auth: None = Depends(autenticar_perfis),
    db: Session = Depends(get_db),
):
    removido = db.execute(
        delete(PapelConta)
        .where(PapelConta.conta_id == conta_id)
        .returning(PapelConta.role)
    ).first()
    if removido is not None:
        _auditar(db, ATOR_PERFIS, "PAPEL_REMOVIDO", papel=removido.role, conta_id=conta_id)
    db.commit()
    return Response(status_code=204)


@app.get("/health")
def health():
    return {"status": "ok"}
