from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.core.config import Settings

SCHEMA_AUTENTICACAO = "autenticacao"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA_AUTENTICACAO)


@lru_cache
def obter_fabrica_sessoes() -> sessionmaker[Session]:
    engine = create_engine(
        Settings().DATABASE_URL.get_secret_value(),
        pool_pre_ping=True,
        hide_parameters=True,
    )
    return sessionmaker(bind=engine)


def get_db() -> Iterator[Session]:
    fabrica = obter_fabrica_sessoes()
    with fabrica() as sessao:
        yield sessao
