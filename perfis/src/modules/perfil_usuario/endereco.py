import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class CamposEndereco:
    """Campos de endereço usados por Endereco (cliente) e por Loja.

    Escritos uma vez só aqui; cada classe que herda ganha essas colunas na
    própria tabela.
    """

    cep: Mapped[str] = mapped_column(String(8))
    logradouro: Mapped[str] = mapped_column(String(150))
    numero: Mapped[str] = mapped_column(String(10))
    complemento: Mapped[str | None] = mapped_column(String(100))
    bairro: Mapped[str] = mapped_column(String(100))
    cidade: Mapped[str] = mapped_column(String(100))
    uf: Mapped[str] = mapped_column(String(2))
    referencia: Mapped[str | None] = mapped_column(String(150))


def restricoes_endereco(prefixo: str) -> tuple[CheckConstraint, ...]:
    """CHECKs de CEP e UF, com nomes próprios para cada tabela."""
    return (
        CheckConstraint("cep ~ '^[0-9]{8}$'", name=f"ck_{prefixo}_cep_8_digitos"),
        CheckConstraint("uf ~ '^[A-Z]{2}$'", name=f"ck_{prefixo}_uf_sigla"),
    )


class Endereco(CamposEndereco, Base):
    """Endereço de cliente. Um cliente pode ter vários (casa, trabalho...).

    O endereço da loja não fica aqui: fica nas colunas da própria tabela
    `lojas`. Entregador e Admin não têm endereço.
    """

    __tablename__ = "enderecos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clientes.id", ondelete="CASCADE"), index=True
    )
    apelido: Mapped[str | None] = mapped_column(String(50))
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
        *restricoes_endereco("endereco"),
        # No máximo um endereço principal por cliente.
        Index(
            "uq_endereco_principal_por_cliente",
            "cliente_id",
            unique=True,
            postgresql_where=text("principal"),
        ),
    )
