import enum
import uuid

from sqlalchemy import CheckConstraint, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .perfil import Perfil, TipoPerfil


class TipoVeiculo(str, enum.Enum):
    BICICLETA = "BICICLETA"
    MOTO = "MOTO"
    CARRO = "CARRO"

class StatusEntregador(str, enum.Enum):
    DISPONIVEL = "DISPONIVEL"
    OCUPADO = "OCUPADO"
    INATIVO = "INATIVO"


class Entregador(Perfil):

    __tablename__ = "entregadores"

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("perfis.id", ondelete="CASCADE"), primary_key=True
    )
    tipo_veiculo: Mapped[TipoVeiculo] = mapped_column(
        Enum(TipoVeiculo, name="tipo_veiculo")
    )
    placa: Mapped[str | None] = mapped_column(String(7),unique=True)
    cnh: Mapped[str | None] = mapped_column(String(11))

    __table_args__ = (
        CheckConstraint(
            "tipo_veiculo = 'BICICLETA' OR (placa IS NOT NULL AND cnh IS NOT NULL)",
            name="ck_entregador_veiculo_motorizado",
        ),
    )

    __mapper_args__ = {
        "polymorphic_identity": TipoPerfil.ENTREGADOR,
        "polymorphic_load": "selectin",
    }