import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from .cliente import Cliente
    from .loja import Loja


class Endereco(Base):
    __tablename__ = "enderecos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cep: Mapped[str] = mapped_column(String(8))
    logradouro: Mapped[str] = mapped_column(String(150))
    numero: Mapped[str] = mapped_column(String(10))
    complemento: Mapped[str | None] = mapped_column(String(100))
    bairro: Mapped[str] = mapped_column(String(100))
    cidade: Mapped[str] = mapped_column(String(100))
    uf: Mapped[str] = mapped_column(String(2))
    referencia: Mapped[str | None] = mapped_column(String(150))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Volta para o dono. Só um dos dois fica preenchido.
    cliente: Mapped["Cliente | None"] = relationship(back_populates="endereco")
    loja: Mapped["Loja | None"] = relationship(back_populates="endereco")

    __table_args__ = (
        CheckConstraint("cep ~ '^[0-9]{8}$'", name="ck_endereco_cep_8_digitos"),
        CheckConstraint("uf ~ '^[A-Z]{2}$'", name="ck_endereco_uf_sigla"),
    )
