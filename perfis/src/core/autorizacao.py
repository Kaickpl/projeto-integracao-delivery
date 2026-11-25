"""Validação local de tokens M2M destinados à leitura de perfis."""
from functools import lru_cache
import re

import httpx
import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWKClientError

from src.core.config import settings


@lru_cache(maxsize=4)
def _cliente_jwks(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_jwk_set=True, lifespan=300)


def exigir_escopo_leitura_perfis(
    authorization: str | None = Header(default=None),
) -> dict:
    esquema, separador, token = (authorization or "").partition(" ")
    if esquema.lower() != "bearer" or not separador or not token.strip():
        raise HTTPException(401, "Token inválido ou expirado")

    try:
        cabecalho = jwt.get_unverified_header(token.strip())
        if cabecalho.get("alg") != "RS256" or cabecalho.get("typ") != "at+jwt":
            raise HTTPException(401, "Token inválido ou expirado")
        jwks_url = f"{settings.AUTENTICACAO_URL.rstrip('/')}/.well-known/jwks.json"
        chave = _cliente_jwks(jwks_url).get_signing_key_from_jwt(token.strip()).key
        claims = jwt.decode(
            token.strip(),
            chave,
            algorithms=["RS256"],
            issuer=settings.AUTHENTICACAO_ISSUER,
            audience=settings.PERFIS_OAUTH_AUDIENCE,
            options={"require": ["iss", "sub", "aud", "iat", "exp", "jti", "client_id", "scope"]},
        )
    except (PyJWKClientConnectionError, httpx.HTTPError, OSError):
        raise HTTPException(503, "Chaves da Identidade indisponíveis") from None
    except (PyJWKClientError, jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(401, "Token inválido ou expirado") from None

    client_id = claims.get("client_id")
    escopos = claims.get("scope")
    if (
        not isinstance(client_id, str)
        or not client_id
        or claims.get("sub") != f"servico:{client_id}"
        or "role" in claims
        or "sid" in claims
        or not isinstance(escopos, str)
        or not escopos.strip()
        or any(not re.fullmatch(r"[!-~]+", item) for item in escopos.split())
    ):
        raise HTTPException(401, "Token inválido ou expirado")
    if settings.PERFIS_READ_SCOPE not in escopos.split():
        raise HTTPException(403, "Escopo insuficiente")
    return claims
