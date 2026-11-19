import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .perfil import Perfil, TipoPerfil


class Admin(Perfil):

    __mapper_args__ = {
        "polymorphic_identity": TipoPerfil.ADMIN,
    }
