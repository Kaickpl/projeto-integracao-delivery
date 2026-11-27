from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    DATABASE_URL: SecretStr
    JWT_PRIVATE_KEY_PATH: Path = Path("./keys/jwt-private.pem")
    JWT_OLD_PUBLIC_KEYS_DIR: Path = Path("./keys/anteriores")
    JWT_KEY_ID: str = "identidade-dev-1"
    JWT_ISSUER: str = "http://localhost:8001"
    JWT_ACCESS_TOKEN_MINUTES: int = 25
    PERFIS_URL: str = "http://perfis:8002"
    PERFIS_STATUS_SERVICE_TOKEN: SecretStr = SecretStr("")
    PERFIS_SERVICE_TOKEN: SecretStr = SecretStr("")
    AUTORIZACAO_URL: str = "http://autorizacao:8003"
    AUTORIZACAO_SERVICE_TOKEN: SecretStr = SecretStr("")
    INTEGRATION_TIMEOUT_SECONDS: float = 2.0
    OAUTH_CLIENT_ID: str = "delivery-app"
    OAUTH_REDIRECT_URI: str = "http://localhost:3000/oauth/callback"
    OAUTH_REDIRECT_URIS: str = ""
    CORS_ORIGENS_PERMITIDAS: str = "http://localhost:3000,http://localhost:5173"
    JWT_AUDIENCE: str = "delivery-api"
    OAUTH_CLIENT_CREDENTIALS_ENABLED: bool = False
    OAUTH_SERVICE_TOKEN_MINUTES: int = 10

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    @field_validator("DATABASE_URL")
    @classmethod
    def validar_driver(cls, valor: SecretStr) -> SecretStr:
        try:
            url = make_url(valor.get_secret_value())
        except (ArgumentError, ValueError):
            raise ValueError("DATABASE_URL inválida") from None
        if url.drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL deve usar postgresql+psycopg://")
        return valor

    @field_validator("JWT_ACCESS_TOKEN_MINUTES")
    @classmethod
    def validar_duracao_token(cls, valor: int) -> int:
        if valor != 25:
            raise ValueError("JWT_ACCESS_TOKEN_MINUTES deve ser 25 conforme os requisitos")
        return valor

    @field_validator("OAUTH_SERVICE_TOKEN_MINUTES")
    @classmethod
    def validar_duracao_token_servico(cls, valor: int) -> int:
        if not 1 <= valor <= 15:
            raise ValueError("OAUTH_SERVICE_TOKEN_MINUTES deve estar entre 1 e 15")
        return valor

    @property
    def oauth_redirect_uris_permitidos(self) -> set[str]:
        return {self.OAUTH_REDIRECT_URI, *(uri.strip() for uri in self.OAUTH_REDIRECT_URIS.split(",") if uri.strip())}
