import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .perfil import Perfil, TipoPerfil


class Admin(Perfil):

    __tablename__ = "admins"

    # Mesmo padrão de Cliente, Loja e Entregador: a linha em `admins` aponta
    # para a linha em `perfis` (classe mãe).
    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("perfis.id", ondelete="CASCADE"), primary_key=True
    )

    __mapper_args__ = {
        "polymorphic_identity": TipoPerfil.ADMIN,
        "polymorphic_load": "selectin",
    }
