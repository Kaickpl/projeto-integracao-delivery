from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateSchema

from src.core.database import Base, SCHEMA, settings
from src.modules import papeis  # noqa: F401

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

URL = settings.DATABASE_URL
OPCOES = {
    "target_metadata": Base.metadata,
    "include_schemas": True,
    "version_table_schema": SCHEMA,
}


def executar_offline():
    context.configure(url=URL, literal_binds=True, dialect_opts={"paramstyle": "named"}, **OPCOES)
    with context.begin_transaction():
        context.execute(CreateSchema(SCHEMA, if_not_exists=True))
        context.run_migrations()


def executar_online():
    engine = create_engine(URL, poolclass=NullPool, hide_parameters=True)
    with engine.begin() as conexao:
        if not inspect(conexao).has_schema(SCHEMA):
            conexao.execute(CreateSchema(SCHEMA))
        context.configure(connection=conexao, **OPCOES)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    executar_offline()
else:
    executar_online()
