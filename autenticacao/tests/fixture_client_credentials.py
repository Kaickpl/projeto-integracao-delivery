"""Prepara fixtures M2M exclusivamente na base descartável da integração."""
import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from src.core.config import Settings
from src.core.security import gerar_hash_senha


def executar() -> None:
    dados = {
        "acao": os.getenv("FIXTURE_ACTION", "preparar"),
        "client_id": os.environ["FIXTURE_CLIENT_ID"],
        "audiencia": os.environ["FIXTURE_AUDIENCE"],
        "escopo": os.environ["FIXTURE_SCOPE"],
        "segredo": os.getenv("FIXTURE_CLIENT_SECRET", ""),
    }
    url = make_url(Settings().DATABASE_URL.get_secret_value())
    if (
        url.drivername != "postgresql+psycopg"
        or url.host != "banco_integracao"
        or not (url.database or "").startswith("delivery_teste")
        or url.username != "integracao_teste"
    ):
        raise RuntimeError("Fixture recusada: banco não corresponde ao PostgreSQL local isolado")

    client_id = dados["client_id"]
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.begin() as connection:
            if dados["acao"] == "preparar":
                connection.execute(
                    text(
                        "INSERT INTO autenticacao.clientes_servico "
                        "(client_id, segredo_hash, ativo) VALUES (:client_id, :hash, TRUE) "
                        "ON CONFLICT (client_id) DO UPDATE SET "
                        "segredo_hash = EXCLUDED.segredo_hash, ativo = TRUE"
                    ),
                    {"client_id": client_id, "hash": gerar_hash_senha(dados["segredo"])},
                )
                connection.execute(
                    text(
                        "INSERT INTO autorizacao.permissoes_clientes_servico "
                        "(client_id, audiencia, escopo) VALUES (:client_id, :audiencia, :escopo) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {
                        "client_id": client_id,
                        "audiencia": dados["audiencia"],
                        "escopo": dados["escopo"],
                    },
                )
            elif dados["acao"] == "limpar":
                connection.execute(
                    text("DELETE FROM autorizacao.permissoes_clientes_servico WHERE client_id = :client_id"),
                    {"client_id": client_id},
                )
                connection.execute(
                    text("DELETE FROM autenticacao.clientes_servico WHERE client_id = :client_id"),
                    {"client_id": client_id},
                )
            else:
                raise ValueError("Ação de fixture inválida")
    finally:
        engine.dispose()
    print("ok")


if __name__ == "__main__":
    executar()
