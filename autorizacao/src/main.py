from functools import lru_cache
import secrets
from typing import Literal
from uuid import UUID
import re

import httpx
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWKClientError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from src.core.database import get_db, settings
from src.modules.papeis import PapelConta, PermissaoClienteServico

PAPEIS = {"CLIENTE", "LOJA", "ENTREGADOR", "ADMIN"}


def autenticar(authorization: str | None, segredo: str) -> None:
    valor = authorization.removeprefix("Bearer ") if authorization else ""
    if not segredo or not secrets.compare_digest(valor, segredo):
        raise HTTPException(401, "Credencial de serviço inválida")


def autenticar_perfis(authorization: str | None = Header(default=None)) -> None:
    autenticar(authorization, settings.INTERNAL_SERVICE_TOKEN.get_secret_value())


def autenticar_auth(authorization: str | None = Header(default=None)) -> None:
    autenticar(authorization, settings.AUTHENTICACAO_SERVICE_TOKEN.get_secret_value())


def _erro(status: int, mensagem: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"erro": True, "mensagem": mensagem},
    )


app = FastAPI(title="Serviço de Autorização e RBAC")


class PapelEntrada(BaseModel):
    role: str


class TokenValidado(BaseModel):
    ativo: bool
    conta_id: UUID
    role: Literal["CLIENTE", "LOJA", "ENTREGADOR", "ADMIN"]
    jti: str


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
        return _erro(503, "Serviço de Autorização indisponível")
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
    summary="Validar token de acesso e estado da sessão",
    description=(
        "Recebe o access token no cabeçalho Bearer, consulta a revogação no Auth "
        "e confirma que o papel continua associado à conta no RBAC."
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
    if (
        esquema.lower() != "bearer"
        or not separador
        or not token.strip()
        or len(token.strip()) > 8192
    ):
        return _erro(401, "Token inválido, expirado ou revogado")

    try:
        resposta = httpx.post(
            f"{settings.AUTHENTICACAO_URL.rstrip('/')}/v1/oauth/introspeccao",
            json={"token": token.strip()},
            headers={
                "Authorization": (
                    "Bearer "
                    + settings.AUTHENTICACAO_SERVICE_TOKEN.get_secret_value()
                )
            },
            timeout=settings.INTEGRATION_TIMEOUT_SECONDS,
        )
        if resposta.status_code != 200:
            return _erro(503, "Serviço de Identidade indisponível")
        dados = resposta.json()
    except (httpx.HTTPError, ValueError):
        return _erro(503, "Serviço de Identidade indisponível")

    if not isinstance(dados, dict) or dados.get("active") is not True:
        return _erro(401, "Token inválido, expirado ou revogado")
    try:
        conta_id = UUID(dados["sub"])
        papel = db.get(PapelConta, conta_id)
    except (KeyError, TypeError, ValueError):
        return _erro(401, "Token inválido, expirado ou revogado")
    except SQLAlchemyError:
        return _erro(503, "Serviço de Autorização indisponível")

    # A associação atual no RBAC é autoritativa. Um token emitido antes de
    # remoção ou mudança de papel não mantém a autorização antiga.
    if (
        papel is None
        or dados.get("role") not in PAPEIS
        or papel.role != dados.get("role")
        or not isinstance(dados.get("jti"), str)
    ):
        return _erro(401, "Token inválido, expirado ou revogado")
    return {
        "ativo": True,
        "conta_id": str(conta_id),
        "role": papel.role,
        "jti": dados["jti"],
    }


@app.get("/v1/interno/contas/{conta_id}/papel")
def consultar_papel(
    conta_id: UUID,
    _auth: None = Depends(autenticar_auth),
    db: Session = Depends(get_db),
):
    papel = db.get(PapelConta, conta_id)
    if papel is None:
        raise HTTPException(404, "Papel não associado")
    return {"conta_id": str(papel.conta_id), "role": papel.role}


@app.get("/v1/interno/clientes/{client_id}/permissoes")
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


@app.put("/v1/interno/contas/{conta_id}/papel")
def associar_papel(
    conta_id: UUID,
    dados: PapelEntrada,
    _auth: None = Depends(autenticar_perfis),
    db: Session = Depends(get_db),
):
    if dados.role not in PAPEIS:
        raise HTTPException(400, "Papel inválido")
    papel = db.get(PapelConta, conta_id)
    if papel is None:
        papel = PapelConta(conta_id=conta_id, role=dados.role)
        db.add(papel)
    else:
        papel.role = dados.role
    db.commit()
    return {"conta_id": str(conta_id), "role": dados.role}


@app.get("/health")
def health():
    return {"status": "ok"}
