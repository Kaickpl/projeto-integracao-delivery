import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class StatusConta(str, enum.Enum):
    PENDENTE_APROVACAO = "PENDENTE_APROVACAO"
    ATIVO = "ATIVO"
    SUSPENSO = "SUSPENSO"


class TipoPerfil(str, enum.Enum):
    CLIENTE = "CLIENTE"
    LOJA = "LOJA"


class Perfil(Base):
    __tablename__ = "perfis"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tipo: Mapped[TipoPerfil] = mapped_column(Enum(TipoPerfil, name="tipo_perfil"))
    nome: Mapped[str] = mapped_column(String(150))
    cpf_cnpj: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    telefone: Mapped[str] = mapped_column(String(20))
    status: Mapped[StatusConta] = mapped_column(
        Enum(StatusConta, name="status_conta"),
        default=StatusConta.PENDENTE_APROVACAO,
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )