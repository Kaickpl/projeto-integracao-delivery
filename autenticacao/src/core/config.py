from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    DATABASE_URL: SecretStr

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
