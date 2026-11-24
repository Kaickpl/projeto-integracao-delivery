import secrets
import re
from html import escape
from uuid import UUID
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from src.core.database import get_db
from src.modules.oauth import service
from src.core.config import Settings
from src.modules.credenciais.repository import RepositorioCredenciais

router = APIRouter(prefix="/v1", tags=["OAuth e autenticação"])


class IntrospeccaoRequest(BaseModel):
    token: str = Field(min_length=1, max_length=8192)


class ErroOAuth(BaseModel):
    erro: bool
    mensagem: str


class CredencialInterna(BaseModel):
    conta_id: UUID
    email: str = Field(min_length=3, max_length=255)
    senha: str = Field(min_length=6, max_length=256)
    tipo_conta: str


def _validar_cliente(client_id: str, redirect_uri: str, response_type: str, method: str) -> None:
    config = Settings()
    if client_id != config.OAUTH_CLIENT_ID or redirect_uri != config.OAUTH_REDIRECT_URI:
        raise HTTPException(400, "Cliente ou endereço de retorno inválido")
    if response_type != "code" or method != "S256":
        raise HTTPException(400, "Authorization Code exige response_type=code e PKCE S256")


def _validar_desafio_pkce(challenge: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", challenge):
        raise HTTPException(400, "Desafio PKCE inválido")


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


@router.post("/interno/credenciais", status_code=201)
def criar_credencial(
    dados: CredencialInterna,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    esperado = Settings().PERFIS_SERVICE_TOKEN.get_secret_value()
    recebido = authorization.removeprefix("Bearer ") if authorization else ""
    if not esperado or not secrets.compare_digest(recebido, esperado):
        raise HTTPException(401, "Credencial de serviço inválida")
    if dados.tipo_conta not in service.PAPEIS_VALIDOS:
        raise HTTPException(400, "Tipo de conta inválido")
    from sqlalchemy.exc import IntegrityError

    try:
        RepositorioCredenciais(db).criar(dados.conta_id, str(dados.email), dados.senha)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "E-mail ou conta já cadastrada") from None
    return {"conta_id": str(dados.conta_id)}


@router.post("/oauth/tokens")
def token(
    grant_type: str = Form(...),
    db: Session = Depends(get_db),
    refresh_token: str | None = Form(default=None),
    code: str | None = Form(default=None),
    code_verifier: str | None = Form(default=None),
    client_id: str | None = Form(default=None),
    redirect_uri: str | None = Form(default=None),
):
    if grant_type == "refresh_token" and refresh_token:
        return service.renovar(db, refresh_token)
    if grant_type == "authorization_code" and all((code, code_verifier, client_id, redirect_uri)):
        return service.trocar_codigo(
            db, code, code_verifier, client_id, redirect_uri
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
