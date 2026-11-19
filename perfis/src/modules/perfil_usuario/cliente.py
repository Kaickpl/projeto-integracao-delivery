import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .endereco import Endereco
from .perfil import Perfil, TipoPerfil


class Cliente(Perfil):

    __tablename__ = "clientes"

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("perfis.id", ondelete="CASCADE"), primary_key=True
    )
    # Opcional: o cliente pode cadastrar o endereço depois. Se o endereço for
    # apagado, a coluna volta a ficar vazia.
    endereco_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("enderecos.id", ondelete="SET NULL", name="fk_clientes_endereco")
    )

    # No máximo um endereço por cliente. Apagar o cliente (pelo SQLAlchemy)
    # apaga o endereço dele junto.
    endereco: Mapped[Endereco | None] = relationship(
        back_populates="cliente",
        cascade="all, delete-orphan",
        single_parent=True,
    )

    __table_args__ = (
        # Um endereço pertence a um cliente só.
        UniqueConstraint("endereco_id", name="uq_clientes_endereco_id"),
    )

    __mapper_args__ = {
        "polymorphic_identity": TipoPerfil.CLIENTE,
        "polymorphic_load": "selectin",
    }
