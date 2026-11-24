import secrets
from typing import Literal
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from src.core.database import get_db, settings
from src.modules.papeis import PapelConta

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
