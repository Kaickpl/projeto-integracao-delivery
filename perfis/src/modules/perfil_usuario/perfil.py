import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.validators import calcular_idade


class StatusConta(str, enum.Enum):
    PENDENTE_APROVACAO = "PENDENTE_APROVACAO"
    ATIVO = "ATIVO"
    SUSPENSO = "SUSPENSO"


class TipoPerfil(str, enum.Enum):
    CLIENTE = "CLIENTE"
    LOJA = "LOJA"
    ENTREGADOR = "ENTREGADOR"
    ADMIN = "ADMIN"


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
    # Cliente, entregador e admin precisam ter 18 anos ou mais; todo cadastro
    # novo deles exige a data. Loja não tem (fica vazio). Perfis criados antes
    # desta regra também ficam vazios até o admin preencher.
    data_nascimento: Mapped[date | None] = mapped_column(Date)
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
    identidade_pronta: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    chave_idempotencia: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), unique=True
    )
    dados_cadastro_hash: Mapped[str | None] = mapped_column(String(64))

    @property
    def idade(self) -> int | None:
        if self.data_nascimento is None:
            return None
        return calcular_idade(self.data_nascimento)

    # `tipo` decide qual subclasse é carregada. `polymorphic_abstract` impede
    # gravar um Perfil genérico: só Cliente, Loja, Entregador e Admin.
    __mapper_args__ = {
        "polymorphic_on": tipo,
        "polymorphic_abstract": True,
    }
