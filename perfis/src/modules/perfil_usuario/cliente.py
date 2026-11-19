import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .endereco import Endereco
from .perfil import Perfil, TipoPerfil


class Cliente(Perfil):

    __tablename__ = "clientes"

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("perfis.id", ondelete="CASCADE"), primary_key=True
    )

    # Um cliente pode ter vários endereços (casa, trabalho...).
    enderecos: Mapped[list[Endereco]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __mapper_args__ = {
        "polymorphic_identity": TipoPerfil.CLIENTE,
        "polymorphic_load": "selectin",
    }
