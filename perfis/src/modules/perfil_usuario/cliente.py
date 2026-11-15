from .perfil import Perfil, TipoPerfil


class Cliente(Perfil):

    __mapper_args__ = {"polymorphic_identity": TipoPerfil.CLIENTE}