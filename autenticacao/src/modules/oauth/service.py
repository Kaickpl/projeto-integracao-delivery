import hashlib
import base64
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import jwt
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import Settings
from src.core.security import verificar_senha
from src.core.tokens import carregar_chave_publica, emitir_access_token
from src.modules.credenciais.repository import RepositorioCredenciais
from src.modules.sessoes.models import CodigoAutorizacao, SessaoRefresh

PAPEIS_VALIDOS = {"CLIENTE", "LOJA", "ENTREGADOR", "ADMIN"}
DIAS_REFRESH = 7


def _consultar_servico(url: str, token: str, caminho: str) -> dict:
    try:
        resposta = httpx.get(
            f"{url.rstrip('/')}{caminho}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=Settings().INTEGRATION_TIMEOUT_SECONDS,
        )
        resposta.raise_for_status()
        return resposta.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(403, "Conta não elegível para autenticação") from None
        raise HTTPException(503, "Serviço de identidade indisponível") from None
    except httpx.HTTPError:
        raise HTTPException(503, "Serviço de identidade indisponível") from None


def obter_status_e_papel(conta_id: UUID) -> tuple[str, str]:
    config = Settings()
    perfil = _consultar_servico(
        config.PERFIS_URL,
        config.PERFIS_STATUS_SERVICE_TOKEN.get_secret_value(),
        f"/v1/interno/contas/{conta_id}/status",
    )
    papel = _consultar_servico(
        config.AUTORIZACAO_URL,
        config.AUTORIZACAO_SERVICE_TOKEN.get_secret_value(),
        f"/v1/interno/contas/{conta_id}/papel",
    )
    status = perfil.get("status")
    role = papel.get("role")
    if status != "ATIVO":
        raise HTTPException(403, "Conta não está ativa")
    if role not in PAPEIS_VALIDOS:
        raise HTTPException(403, "Papel da conta inválido")
    return status, role


def _novo_refresh(db: Session, conta_id: UUID, client_id: str, audience: str, sessao_id: UUID | None = None):
    agora = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(48)
    registro = SessaoRefresh(
        id=uuid4(),
        sessao_id=sessao_id or uuid4(),
        conta_id=conta_id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        client_id=client_id,
        audiencia=audience,
        expira_em=agora + timedelta(days=DIAS_REFRESH),
    )
    db.add(registro)
    db.flush()
    return token, registro


def emitir_par(db: Session, conta_id: UUID, role: str, client_id: str, audience: str):
    refresh, registro = _novo_refresh(db, conta_id, client_id, audience)
    access = emitir_access_token(conta_id, role, audience, client_id, sessao_id=registro.sessao_id)
    return {"access_token": access, "refresh_token": refresh, "token_type": "Bearer", "expires_in": 1500}


def login(db: Session, email: str, senha: str, client_id: str, audience: str):
    credencial = RepositorioCredenciais(db).buscar_por_email(email)
    if not credencial or not verificar_senha(senha, credencial.senha_hash):
        raise HTTPException(401, "Usuário ou senha inválidos")
    _, role = obter_status_e_papel(credencial.conta_id)
    resposta = emitir_par(db, credencial.conta_id, role, client_id, audience)
    db.commit()
    return resposta


def renovar(db: Session, token: str):
    digest = hashlib.sha256(token.encode()).hexdigest()
    registro = db.scalar(
        select(SessaoRefresh).where(SessaoRefresh.token_hash == digest).with_for_update()
    )
    agora = datetime.now(timezone.utc)
    if registro is None:
        raise HTTPException(401, "Refresh token inválido")
    if registro.revogado_em is not None:
        db.query(SessaoRefresh).filter(SessaoRefresh.sessao_id == registro.sessao_id).update(
            {SessaoRefresh.revogado_em: agora}, synchronize_session=False
        )
        db.commit()
        raise HTTPException(401, "Sessão revogada")
    if registro.expira_em <= agora:
        registro.revogado_em = agora
        db.commit()
        raise HTTPException(401, "Refresh token expirado")

    try:
        _, role = obter_status_e_papel(registro.conta_id)
    except HTTPException as exc:
        if exc.status_code == 403:
            db.query(SessaoRefresh).filter(SessaoRefresh.sessao_id == registro.sessao_id).update(
                {SessaoRefresh.revogado_em: agora}, synchronize_session=False
            )
            db.commit()
        raise
    registro.revogado_em = agora
    refresh, substituto = _novo_refresh(
        db, registro.conta_id, registro.client_id, registro.audiencia, registro.sessao_id
    )
    registro.substituido_por_id = substituto.id
    access = emitir_access_token(
        registro.conta_id, role, registro.audiencia, registro.client_id,
        sessao_id=registro.sessao_id,
    )
    db.commit()
    return {"access_token": access, "refresh_token": refresh, "token_type": "Bearer", "expires_in": 1500}


def revogar(db: Session, token: str) -> dict:
    """Revoga a família associada ao refresh token, sem revelar se ele existe."""
    digest = hashlib.sha256(token.encode()).hexdigest()
    registro = db.scalar(
        select(SessaoRefresh)
        .where(SessaoRefresh.token_hash == digest)
        .with_for_update()
    )
    if registro is None:
        return {}
    agora = datetime.now(timezone.utc)
    db.query(SessaoRefresh).filter(
        SessaoRefresh.sessao_id == registro.sessao_id,
        SessaoRefresh.revogado_em.is_(None),
    ).update({SessaoRefresh.revogado_em: agora}, synchronize_session=False)
    db.commit()
    return {}


def autorizar(db: Session, email: str, senha: str, client_id: str, redirect_uri: str, challenge: str):
    config = Settings()
    if client_id != config.OAUTH_CLIENT_ID or redirect_uri != config.OAUTH_REDIRECT_URI:
        raise HTTPException(400, "Cliente ou endereço de retorno inválido")
    credencial = RepositorioCredenciais(db).buscar_por_email(email)
    if not credencial or not verificar_senha(senha, credencial.senha_hash):
        raise HTTPException(401, "Usuário ou senha inválidos")
    _, _role = obter_status_e_papel(credencial.conta_id)
    codigo = secrets.token_urlsafe(32)
    db.add(CodigoAutorizacao(
        id=uuid4(),
        codigo_hash=hashlib.sha256(codigo.encode()).hexdigest(),
        conta_id=credencial.conta_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=challenge,
        expira_em=datetime.now(timezone.utc) + timedelta(minutes=3),
    ))
    db.commit()
    return codigo


def trocar_codigo(db: Session, codigo: str, verifier: str, client_id: str, redirect_uri: str):
    if not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier):
        raise HTTPException(400, "Verificador PKCE inválido")
    config = Settings()
    if client_id != config.OAUTH_CLIENT_ID or redirect_uri != config.OAUTH_REDIRECT_URI:
        raise HTTPException(400, "Cliente ou endereço de retorno inválido")
    registro = db.scalar(
        select(CodigoAutorizacao)
        .where(CodigoAutorizacao.codigo_hash == hashlib.sha256(codigo.encode()).hexdigest())
        .with_for_update()
    )
    agora = datetime.now(timezone.utc)
    if registro is None or registro.usado_em is not None or registro.expira_em <= agora:
        raise HTTPException(400, "Código de autorização inválido ou expirado")
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    if not secrets.compare_digest(desafio, registro.code_challenge):
        raise HTTPException(400, "Verificador PKCE inválido")
    _, role = obter_status_e_papel(registro.conta_id)
    registro.usado_em = agora
    resposta = emitir_par(db, registro.conta_id, role, client_id, config.JWT_AUDIENCE)
    db.commit()
    return resposta


def introspeccionar(db: Session, token: str) -> dict:
    config = Settings()
    try:
        header = jwt.get_unverified_header(token)
        claims = jwt.decode(
            token,
            carregar_chave_publica(header.get("kid", "")),
            algorithms=["RS256"],
            issuer=config.JWT_ISSUER,
            audience=config.JWT_AUDIENCE,
            options={"require": ["exp", "iat", "sub", "jti", "sid"]},
        )
        sessao_id = UUID(claims["sid"])
        ativa = db.scalar(
            select(SessaoRefresh.id).where(
                SessaoRefresh.sessao_id == sessao_id,
                SessaoRefresh.revogado_em.is_(None),
                SessaoRefresh.expira_em > datetime.now(timezone.utc),
            ).limit(1)
        ) is not None
        return {"active": ativa, "sub": claims["sub"], "jti": claims["jti"]}
    except (jwt.InvalidTokenError, KeyError, ValueError, OSError):
        return {"active": False}
