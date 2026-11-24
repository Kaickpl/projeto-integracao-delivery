from fastapi import FastAPI

from src.core.config import Settings
from src.core.tokens import documento_jwks
from src.modules.oauth.router import router as oauth_router

app = FastAPI()
app.include_router(oauth_router)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/.well-known/jwks.json", include_in_schema=False)
def jwks():
    return documento_jwks()


@app.get("/.well-known/oauth-authorization-server", include_in_schema=False)
def metadados_oauth():
    config = Settings()
    base = config.JWT_ISSUER.rstrip("/")
    return {
        "issuer": config.JWT_ISSUER,
        "authorization_endpoint": f"{base}/v1/oauth/autorizar",
        "token_endpoint": f"{base}/v1/oauth/tokens",
        "revocation_endpoint": f"{base}/v1/oauth/revogar",
        "introspection_endpoint": f"{base}/v1/oauth/introspeccao",
        "jwks_uri": f"{base}/.well-known/jwks.json",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }
