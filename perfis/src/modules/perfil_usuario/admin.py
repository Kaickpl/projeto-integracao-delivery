from .perfil import Perfil, TipoPerfil


class Admin(Perfil):

    __mapper_args__ = {"polymorphic_identity": TipoPerfil.ADMIN}