from sqlalchemy.orm import Mapped, relationship

from .endereco import Endereco
from .perfil import Perfil, TipoPerfil


class Cliente(Perfil):

    # Um cliente pode ter vários endereços (casa, trabalho...).
    enderecos: Mapped[list[Endereco]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __mapper_args__ = {"polymorphic_identity": TipoPerfil.CLIENTE}
