from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    INTERNAL_SERVICE_TOKEN: str = ""
    AUTENTICACAO_URL: str = "http://autenticacao:8001"
    AUTENTICACAO_SERVICE_TOKEN: str = ""
    AUTORIZACAO_URL: str = "http://autorizacao:8003"
    AUTORIZACAO_SERVICE_TOKEN: str = ""
    PERFIS_OAUTH_AUDIENCE: str = "http://perfis:8002"
    PERFIS_READ_SCOPE: str = "perfis:ler"
    AUTHENTICACAO_ISSUER: str = "http://localhost:8001"
    VIACEP_URL: str = "https://viacep.com.br/ws"
    VIACEP_TIMEOUT: float = 5.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
