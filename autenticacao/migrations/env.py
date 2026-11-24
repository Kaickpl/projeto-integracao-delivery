from alembic import context
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateSchema

from src.core.config import Settings
from src.core.database import Base, SCHEMA_AUTENTICACAO
from src.modules.credenciais import models  # noqa: F401
from src.modules.sessoes import models as sessoes_models  # noqa: F401


def incluir_schema(nome, tipo, _nomes_pai):
    return tipo != "schema" or nome == SCHEMA_AUTENTICACAO


opcoes = {
    "target_metadata": Base.metadata,
    "include_schemas": True,
    "include_name": incluir_schema,
    "version_table_schema": SCHEMA_AUTENTICACAO,
}
database_url = Settings().DATABASE_URL.get_secret_value()


if context.is_offline_mode():
    context.configure(url=database_url, literal_binds=True, **opcoes)
    with context.begin_transaction():
        context.execute(CreateSchema(SCHEMA_AUTENTICACAO, if_not_exists=True))
        context.run_migrations()
else:
    engine = create_engine(database_url, poolclass=NullPool, hide_parameters=True)
    with engine.begin() as conexao:
        # O Alembic precisa do schema antes de criar a tabela de versões.
        if not inspect(conexao).has_schema(SCHEMA_AUTENTICACAO):
            conexao.execute(CreateSchema(SCHEMA_AUTENTICACAO))
        context.configure(connection=conexao, **opcoes)
        context.run_migrations()
