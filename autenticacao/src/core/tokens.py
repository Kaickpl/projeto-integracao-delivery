"""Assinatura de access tokens e publicação pública de chaves RS256."""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from src.core.config import Settings


@lru_cache
def _carregar_chave_privada(caminho: str, mtime_ns: int) -> RSAPrivateKey:
    del mtime_ns  # Invalidar cache quando a chave for rotacionada no arquivo.
    chave = serialization.load_pem_private_key(Path(caminho).read_bytes(), password=None)
    if not isinstance(chave, RSAPrivateKey):
        raise ValueError("A chave privada JWT precisa ser RSA")
    if chave.key_size < 2048:
        raise ValueError("A chave RSA precisa ter pelo menos 2048 bits")
    return chave


def emitir_access_token(
    conta_id: UUID,
    role: str,
    audience: str,
    client_id: str,
    *,
    agora: datetime | None = None,
    sessao_id: UUID | None = None,
) -> str:
    config = Settings()
    chave_path = config.JWT_PRIVATE_KEY_PATH
    chave = _carregar_chave_privada(str(chave_path), chave_path.stat().st_mtime_ns)
    inicio = agora or datetime.now(timezone.utc)
    claims = {
        "iss": config.JWT_ISSUER,
        "sub": str(conta_id),
        "aud": audience,
        "iat": inicio,
        "exp": inicio + timedelta(minutes=config.JWT_ACCESS_TOKEN_MINUTES),
        "jti": str(uuid4()),
        "client_id": client_id,
        "role": role,
        **({"sid": str(sessao_id)} if sessao_id else {}),
    }
    return jwt.encode(
        claims,
        chave,
        algorithm="RS256",
        headers={"kid": config.JWT_KEY_ID, "typ": "at+jwt"},
    )


def emitir_access_token_servico(
    client_id: str,
    audiencia: str,
    escopos: list[str],
    *,
    agora: datetime | None = None,
) -> str:
    """Emite JWT M2M sem papel ou identificador de sessão de usuário."""
    config = Settings()
    chave_path = config.JWT_PRIVATE_KEY_PATH
    chave = _carregar_chave_privada(str(chave_path), chave_path.stat().st_mtime_ns)
    inicio = agora or datetime.now(timezone.utc)
    claims = {
        "iss": config.JWT_ISSUER,
        "sub": f"servico:{client_id}",
        "aud": audiencia,
        "iat": inicio,
        "exp": inicio + timedelta(minutes=config.OAUTH_SERVICE_TOKEN_MINUTES),
        "jti": str(uuid4()),
        "client_id": client_id,
        "scope": " ".join(sorted(set(escopos))),
    }
    return jwt.encode(
        claims,
        chave,
        algorithm="RS256",
        headers={"kid": config.JWT_KEY_ID, "typ": "at+jwt"},
    )


def documento_jwks() -> dict[str, list[dict[str, Any]]]:
    config = Settings()
    chave_path = config.JWT_PRIVATE_KEY_PATH
    chave = _carregar_chave_privada(str(chave_path), chave_path.stat().st_mtime_ns)
    chave_publica = chave.public_key()
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(chave_publica, as_dict=True)
    jwk.update({"kid": config.JWT_KEY_ID, "use": "sig", "alg": "RS256"})
    chaves = [jwk]
    for arquivo in sorted(config.JWT_OLD_PUBLIC_KEYS_DIR.glob("*.pem")):
        chave_antiga = serialization.load_pem_public_key(arquivo.read_bytes())
        if not isinstance(chave_antiga, type(chave_publica)):
            raise ValueError("Chave pública legada não é RSA")
        jwk_antiga = jwt.algorithms.RSAAlgorithm.to_jwk(chave_antiga, as_dict=True)
        jwk_antiga.update({"kid": arquivo.stem, "use": "sig", "alg": "RS256"})
        chaves.append(jwk_antiga)
    return {"keys": chaves}


def carregar_chave_publica(kid: str):
    config = Settings()
    chave_path = config.JWT_PRIVATE_KEY_PATH
    chave_atual = _carregar_chave_privada(str(chave_path), chave_path.stat().st_mtime_ns)
    if kid == config.JWT_KEY_ID:
        return chave_atual.public_key()
    arquivo = config.JWT_OLD_PUBLIC_KEYS_DIR / f"{kid}.pem"
    chave = serialization.load_pem_public_key(arquivo.read_bytes())
    if not isinstance(chave, RSAPublicKey) or chave.key_size < 2048:
        raise ValueError("Chave pública antiga inválida")
    return chave
