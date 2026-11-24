from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class PapelConta(Base):
    __tablename__ = "papeis_conta"
    __table_args__ = (
        CheckConstraint(
            "role IN ('CLIENTE', 'LOJA', 'ENTREGADOR', 'ADMIN')",
            name="ck_papeis_conta_role_valido",
        ),
    )

    conta_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)


class PermissaoClienteServico(Base):
    __tablename__ = "permissoes_clientes_servico"

    client_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    audiencia: Mapped[str] = mapped_column(String(500), primary_key=True)
    escopo: Mapped[str] = mapped_column(String(120), primary_key=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
