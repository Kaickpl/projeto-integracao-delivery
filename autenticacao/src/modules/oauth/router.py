import base64
import binascii
import secrets
import re
from html import escape
from uuid import UUID
from urllib.parse import parse_qsl, unquote_plus, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.responses import Response

from src.core.database import get_db
from src.core.security import verificar_senha
from src.modules.oauth import service
from src.core.config import Settings
from src.modules.credenciais.repository import RepositorioCredenciais

router = APIRouter(prefix="/v1", tags=["OAuth e autenticação"])


class IntrospeccaoRequest(BaseModel):
    token: str = Field(min_length=1, max_length=8192)


class ErroOAuth(BaseModel):
    erro: bool
    mensagem: str
    error: str | None = None


def _erro_oauth_token(
    status: int,
    codigo: str,
    mensagem: str,
    cabecalhos: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"erro": True, "mensagem": mensagem, "error": codigo},
        headers=cabecalhos,
    )


class CredencialInterna(BaseModel):
    conta_id: UUID = Field(examples=["00000000-0000-4000-8000-000000000001"])
    email: EmailStr = Field(examples=["cliente@example.com"])
    senha: str = Field(min_length=6, max_length=256, examples=["senha-ficticia"])
    tipo_conta: str = Field(examples=["CLIENTE"])

    @field_validator("email", mode="before")
    @classmethod
    def validar_comprimento_email(cls, email: object) -> object:
        if isinstance(email, str) and len(email) > 255:
            raise ValueError("E-mail deve ter até 255 caracteres")
        return email


class CredencialCriada(BaseModel):
    conta_id: UUID


class ErroCredencialInterna(BaseModel):
    detail: str


bearer_perfis = HTTPBearer(
    scheme_name="CredencialServicoPerfis",
    description="Token interno dedicado ao serviço de Perfis.",
    auto_error=False,
)


def _validar_cliente(client_id: str, redirect_uri: str, response_type: str, method: str) -> None:
    config = Settings()
    if client_id != config.OAUTH_CLIENT_ID or redirect_uri not in getattr(
        config, "oauth_redirect_uris_permitidos", {config.OAUTH_REDIRECT_URI}
    ):
        raise HTTPException(400, "Cliente ou endereço de retorno inválido")
    if response_type != "code" or method != "S256":
        raise HTTPException(400, "Authorization Code exige response_type=code e PKCE S256")


def _validar_desafio_pkce(challenge: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", challenge):
        raise HTTPException(400, "Desafio PKCE inválido")


def _extrair_client_secret_basic(authorization: str | None) -> tuple[str, str] | None:
    esquema, separador, valor = (authorization or "").partition(" ")
    if esquema.lower() != "basic" or not separador or not valor.strip():
        return None
    try:
        decodificado = base64.b64decode(valor.strip(), validate=True).decode("utf-8")
        client_id_codificado, delimitador, segredo_codificado = decodificado.partition(":")
        if not delimitador or not client_id_codificado or not segredo_codificado:
            return None
        client_id = unquote_plus(client_id_codificado)
        segredo = unquote_plus(segredo_codificado)
        if not client_id or not segredo or len(client_id) > 120 or len(segredo) > 512:
            return None
        return client_id, segredo
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


@router.get("/oauth/autorizar", response_class=HTMLResponse)
def pagina_autorizacao(
    client_id: str,
    redirect_uri: str,
    response_type: str,
    code_challenge: str = Query(min_length=43, max_length=128),
    code_challenge_method: str = "S256",
    state: str = Query(min_length=1, max_length=256),
):
    _validar_cliente(client_id, redirect_uri, response_type, code_challenge_method)
    _validar_desafio_pkce(code_challenge)
    return HTMLResponse(
        """<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Entrar</title>
<h1>Entrar na Identidade</h1><form method="post" action="/v1/oauth/entrar">
<label>E-mail <input name="email" type="email" required autocomplete="username"></label>
<label>Senha <input name="senha" type="password" required autocomplete="current-password"></label>
<input type="hidden" name="client_id" value="%s"><input type="hidden" name="redirect_uri" value="%s">
<input type="hidden" name="response_type" value="code"><input type="hidden" name="code_challenge" value="%s">
<input type="hidden" name="code_challenge_method" value="S256"><input type="hidden" name="state" value="%s">
<button type="submit">Entrar</button></form></html>"""
        % tuple(map(escape, (client_id, redirect_uri, code_challenge, state)))
    )


@router.post("/oauth/entrar")
def entrar(
    email: str = Form(...),
    senha: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    response_type: str = Form(...),
    code_challenge: str = Form(...),
    code_challenge_method: str = Form(...),
    state: str = Form(...),
    db: Session = Depends(get_db),
):
    _validar_cliente(client_id, redirect_uri, response_type, code_challenge_method)
    _validar_desafio_pkce(code_challenge)
    codigo = service.autorizar(
        db, email, senha, client_id, redirect_uri, code_challenge
    )
    parsed = urlsplit(redirect_uri)
    query = [
        (chave, valor)
        for chave, valor in parse_qsl(parsed.query, keep_blank_values=True)
        if chave not in {"code", "state"}
    ]
    query.extend((("code", codigo), ("state", state)))
    return RedirectResponse(
        url=urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)),
        status_code=303,
    )


@router.post(
    "/interno/credenciais",
    status_code=201,
    response_model=CredencialCriada,
    summary="Provisionar credencial de um perfil (INT-02)",
    description="Perfis envia o UUID do perfil. Repetir a mesma conta, e-mail e senha é idempotente.",
    responses={
        200: {"model": CredencialCriada, "description": "Credencial já provisionada"},
        400: {"model": ErroCredencialInterna, "description": "Tipo de conta inválido"},
        401: {"model": ErroCredencialInterna, "description": "Credencial de serviço inválida"},
        409: {"model": ErroCredencialInterna, "description": "E-mail ou conta em conflito"},
        422: {"description": "Dados inválidos; a resposta omite os valores enviados"},
    },
)
def criar_credencial(
    dados: CredencialInterna,
    authorization: HTTPAuthorizationCredentials | None = Security(bearer_perfis),
    db: Session = Depends(get_db),
):
    esperado = Settings().PERFIS_SERVICE_TOKEN.get_secret_value()
    recebido = authorization.credentials if authorization else ""
    if not esperado or not secrets.compare_digest(recebido.encode(), esperado.encode()):
        raise HTTPException(401, "Credencial de serviço inválida")
    if dados.tipo_conta not in service.PAPEIS_VALIDOS:
        raise HTTPException(400, "Tipo de conta inválido")
    repositorio = RepositorioCredenciais(db)
    existente = repositorio.buscar_por_conta_id(dados.conta_id)
    if existente is not None:
        if (
            existente.email.casefold() == dados.email.casefold()
            and verificar_senha(dados.senha, existente.senha_hash)
        ):
            return JSONResponse(status_code=200, content={"conta_id": str(dados.conta_id)})
        raise HTTPException(409, "Conta já provisionada com outros dados")
    if repositorio.buscar_por_email(dados.email) is not None:
        raise HTTPException(409, "E-mail ou conta já cadastrada")

    from sqlalchemy.exc import IntegrityError
    try:
        repositorio.criar(dados.conta_id, str(dados.email), dados.senha)
        db.commit()
    except IntegrityError:
        db.rollback()
        existente = repositorio.buscar_por_conta_id(dados.conta_id)
        if (
            existente is not None
            and existente.email.casefold() == dados.email.casefold()
            and verificar_senha(dados.senha, existente.senha_hash)
        ):
            return JSONResponse(status_code=200, content={"conta_id": str(dados.conta_id)})
        raise HTTPException(409, "E-mail ou conta já cadastrada") from None
    return {"conta_id": str(dados.conta_id)}


@router.delete(
    "/interno/credenciais/{conta_id}",
    status_code=204,
    summary="Remover credenciais e revogar sessões de uma conta",
    description="Operação interna idempotente, autenticada pelo serviço de Perfis.",
    responses={401: {"model": ErroCredencialInterna}, 503: {"model": ErroCredencialInterna}},
)
def remover_credencial(
    conta_id: UUID,
    authorization: HTTPAuthorizationCredentials | None = Security(bearer_perfis),
    db: Session = Depends(get_db),
) -> Response:
    esperado = Settings().PERFIS_SERVICE_TOKEN.get_secret_value()
    recebido = authorization.credentials if authorization else ""
    if not esperado or not secrets.compare_digest(recebido.encode(), esperado.encode()):
        raise HTTPException(401, "Credencial de serviço inválida")
    try:
        service.remover_credencial_e_revogar_sessoes(db, conta_id)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Não foi possível remover as credenciais da conta") from None
    return Response(status_code=204)


@router.post(
    "/oauth/tokens",
    summary="Emitir, renovar ou trocar tokens OAuth",
    description=(
        "Troca Authorization Code com PKCE ou refresh token. Quando habilitado, "
        "aceita Client Credentials via HTTP Basic, resource e scope."
    ),
    responses={
        400: {"model": ErroOAuth, "description": "Grant ou parâmetros inválidos"},
        401: {"model": ErroOAuth, "description": "Cliente ou segredo inválido"},
        403: {"model": ErroOAuth, "description": "Audiência ou escopo não autorizado"},
        503: {"model": ErroOAuth, "description": "RBAC indisponível"},
    },
)
def token(
    grant_type: str = Form(...),
    db: Session = Depends(get_db),
    refresh_token: str | None = Form(default=None),
    code: str | None = Form(default=None),
    code_verifier: str | None = Form(default=None),
    client_id: str | None = Form(default=None),
    redirect_uri: str | None = Form(default=None),
    resource: str | None = Form(default=None, max_length=500),
    scope: str | None = Form(default=None, max_length=2000),
    authorization: str | None = Header(default=None),
):
    if grant_type == "refresh_token" and refresh_token:
        return service.renovar(db, refresh_token)
    if grant_type == "authorization_code" and all((code, code_verifier, client_id, redirect_uri)):
        return service.trocar_codigo(
            db, code, code_verifier, client_id, redirect_uri
        )
    if grant_type == "client_credentials":
        config = Settings()
        if not config.OAUTH_CLIENT_CREDENTIALS_ENABLED:
            return _erro_oauth_token(400, "unsupported_grant_type", "Grant não habilitado")
        credenciais = _extrair_client_secret_basic(authorization)
        if credenciais is None:
            return _erro_oauth_token(
                401,
                "invalid_client",
                "Cliente ou segredo inválido",
                {"WWW-Authenticate": 'Basic realm="token"'},
            )
        if not resource or not scope:
            return _erro_oauth_token(400, "invalid_request", "resource e scope são obrigatórios")
        recurso = urlsplit(resource)
        if not recurso.scheme or not recurso.netloc or recurso.fragment:
            return _erro_oauth_token(
                400,
                "invalid_target",
                "resource deve ser uma URI absoluta sem fragmento",
            )
        escopos = scope.split()
        if not escopos or len(set(escopos)) != len(escopos):
            return _erro_oauth_token(400, "invalid_scope", "Escopos inválidos ou repetidos")
        if any(
            not re.fullmatch(r"[!-~]+", item) or '"' in item or "\\" in item
            for item in escopos
        ):
            return _erro_oauth_token(400, "invalid_scope", "Formato de escopo inválido")
        try:
            return service.emitir_token_cliente_servico(
                db, credenciais[0], credenciais[1], resource, escopos
            )
        except service.EscopoClienteNaoAutorizado as exc:
            return _erro_oauth_token(400, "invalid_scope", str(exc.detail))
        except HTTPException as exc:
            codigo = {
                400: "invalid_request",
                401: "invalid_client",
                403: "invalid_scope",
                503: "server_error",
            }.get(exc.status_code, "server_error")
            status = 400 if codigo == "invalid_scope" else exc.status_code
            headers = {"WWW-Authenticate": 'Basic realm="token"'} if codigo == "invalid_client" else None
            return _erro_oauth_token(status, codigo, str(exc.detail), headers)
        except SQLAlchemyError:
            return _erro_oauth_token(
                503,
                "server_error",
                "Serviço de autenticação indisponível",
            )
    raise HTTPException(400, "grant_type inválido")


@router.post(
    "/oauth/revogar",
    status_code=200,
    summary="Revogar sessão OAuth",
    description=(
        "Aceita um refresh token ou access token assinado e revoga a família "
        "inteira da sessão. O resultado não revela se o token era conhecido."
    ),
    responses={
        503: {"model": ErroOAuth, "description": "A revogação não pôde ser persistida"},
    },
)
def revogar(
    token: str = Form(..., min_length=1, max_length=8192),
    token_type_hint: str | None = Form(default=None, max_length=100),
    db: Session = Depends(get_db),
):
    # RFC 7009 permite ignorar uma indicação de tipo desconhecida. O serviço
    # identifica refresh tokens opacos e access tokens assinados pela própria
    # sessão, sem revelar se o valor recebido era conhecido.
    del token_type_hint
    try:
        return service.revogar(db, token)
    except SQLAlchemyError:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        return JSONResponse(
            status_code=503,
            content={"erro": True, "mensagem": "Não foi possível confirmar a revogação"},
        )


@router.post("/oauth/introspeccao")
def introspeccionar(
    dados: IntrospeccaoRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    esperado = Settings().AUTORIZACAO_SERVICE_TOKEN.get_secret_value()
    recebido = authorization.removeprefix("Bearer ") if authorization else ""
    if not esperado or not secrets.compare_digest(recebido, esperado):
        raise HTTPException(401, "Credencial de serviço inválida")
    return service.introspeccionar(db, dados.token)
