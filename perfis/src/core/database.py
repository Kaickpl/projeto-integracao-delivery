from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.core.config import settings
from src.core.exceptions import DadoDuplicado

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Restrições de unicidade do banco -> mensagem para o usuário.
MENSAGENS_DE_DUPLICIDADE = {
    "ix_perfis_cpf_cnpj": "CPF/CNPJ já cadastrado",
    "ix_perfis_email": "E-mail já cadastrado",
    "entregadores_placa_key": "Placa já cadastrada",
}


def salvar_alteracoes(db: Session) -> None:
    """Faz o commit e, se algo repetido for recusado, diz o que repetiu."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # 23505 = unique_violation. Outras violações não são "duplicado".
        if getattr(exc.orig, "sqlstate", None) != "23505":
            raise
        restricao = exc.orig.diag.constraint_name
        raise DadoDuplicado(MENSAGENS_DE_DUPLICIDADE.get(restricao)) from exc
