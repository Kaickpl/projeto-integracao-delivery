import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .perfil import Perfil, TipoPerfil


class Loja(Perfil):


    __tablename__ = "lojas"

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("perfis.id", ondelete="CASCADE"), primary_key=True
    )
    razao_social: Mapped[str] = mapped_column(String(150))

    __mapper_args__ = {
        "polymorphic_identity": TipoPerfil.LOJA,
        "polymorphic_load": "selectin",
    }