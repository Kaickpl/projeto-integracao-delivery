from pathlib import Path

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SCHEMA = "autorizacao"


class Settings(BaseSettings):
    DATABASE_URL: str
    INTERNAL_SERVICE_TOKEN: SecretStr = SecretStr("")
    AUTHENTICACAO_SERVICE_TOKEN: SecretStr = SecretStr("")
    AUTHENTICACAO_URL: str = "http://autenticacao:8001"
    AUTHENTICACAO_ISSUER: str = "http://localhost:8001"
    INTEGRATION_TIMEOUT_SECONDS: float = 2.0

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, hide_parameters=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
