import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base

from .perfil import TipoPerfil


class Endereco(Base):
    __tablename__ = "enderecos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    perfil_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    # Preenchido pelo relacionamento (Cliente.enderecos / Loja.endereco).
    perfil_tipo: Mapped[TipoPerfil] = mapped_column(
        Enum(TipoPerfil, name="tipo_perfil")
    )
    apelido: Mapped[str | None] = mapped_column(String(50))
    cep: Mapped[str] = mapped_column(String(8))
    logradouro: Mapped[str] = mapped_column(String(150))
    numero: Mapped[str] = mapped_column(String(10))
    complemento: Mapped[str | None] = mapped_column(String(100))
    bairro: Mapped[str] = mapped_column(String(100))
    cidade: Mapped[str] = mapped_column(String(100))
    uf: Mapped[str] = mapped_column(String(2))
    referencia: Mapped[str | None] = mapped_column(String(150))
    principal: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["perfil_id", "perfil_tipo"],
            ["perfis.id", "perfis.tipo"],
            ondelete="CASCADE",
            name="fk_enderecos_perfil",
        ),
        CheckConstraint(
            "perfil_tipo IN ('CLIENTE', 'LOJA')",
            name="ck_endereco_somente_cliente_ou_loja",
        ),
        CheckConstraint("cep ~ '^[0-9]{8}$'", name="ck_endereco_cep_8_digitos"),
        CheckConstraint("uf ~ '^[A-Z]{2}$'", name="ck_endereco_uf_sigla"),
        Index(
            "uq_endereco_principal_por_perfil",
            "perfil_id",
            unique=True,
            postgresql_where=text("principal"),
        ),
        Index(
            "uq_endereco_unico_por_loja",
            "perfil_id",
            unique=True,
            postgresql_where=text("perfil_tipo = 'LOJA'"),
        ),
    )
