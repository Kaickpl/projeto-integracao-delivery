import enum
import uuid
from datetime import time

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class DiaSemana(str, enum.Enum):
    SEGUNDA = "SEGUNDA"
    TERCA = "TERCA"
    QUARTA = "QUARTA"
    QUINTA = "QUINTA"
    SEXTA = "SEXTA"
    SABADO = "SABADO"
    DOMINGO = "DOMINGO"


class HorarioFuncionamento(Base):
    """Um intervalo em que a loja funciona num dia da semana.

    Um dia pode ter mais de um intervalo (ex.: almoço e jantar). Os horários
    são no horário local da loja. Se `fecha` for menor que `abre`, o
    intervalo passa da meia-noite (ex.: 18:00 às 02:00).
    """

    __tablename__ = "horarios_funcionamento"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    loja_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lojas.id", ondelete="CASCADE"), index=True
    )
    dia_semana: Mapped[DiaSemana] = mapped_column(Enum(DiaSemana, name="dia_semana"))
    abre: Mapped[time] = mapped_column(Time)
    fecha: Mapped[time] = mapped_column(Time)

    __table_args__ = (
        UniqueConstraint("loja_id", "dia_semana", "abre", name="uq_horario_loja_dia_abre"),
        CheckConstraint("abre <> fecha", name="ck_horario_abre_diferente_de_fecha"),
    )
