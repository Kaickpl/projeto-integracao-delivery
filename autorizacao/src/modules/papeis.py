from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base

PAPEIS = ("CLIENTE", "LOJA", "ENTREGADOR", "ADMIN")
_PAPEIS_SQL = ", ".join(f"'{papel}'" for papel in PAPEIS)

# Permissão que dá acesso às rotas de gestão. Nunca pode sair do papel ADMIN,
# senão ninguém mais consegue gerir as permissões.
PERMISSAO_GESTAO = "rbac:gerenciar"

ACOES_AUDITORIA = (
    "PERMISSAO_CONCEDIDA",
    "PERMISSAO_REMOVIDA",
    "PAPEL_ASSOCIADO",
    "PAPEL_REMOVIDO",
)


class PapelConta(Base):
    __tablename__ = "papeis_conta"
    __table_args__ = (
        CheckConstraint(
            f"role IN ({_PAPEIS_SQL})",
            name="ck_papeis_conta_role_valido",
        ),
    )

    conta_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)


class PermissaoClienteServico(Base):
    __tablename__ = "permissoes_clientes_servico"

    client_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    audiencia: Mapped[str] = mapped_column(String(500), primary_key=True)
    escopo: Mapped[str] = mapped_column(String(120), primary_key=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Permissao(Base):
    """Catálogo de permissões de usuário. É fixo e vem da migração."""

    __tablename__ = "permissoes"

    codigo: Mapped[str] = mapped_column(String(80), primary_key=True)
    descricao: Mapped[str] = mapped_column(String(255), nullable=False)


class PapelPermissao(Base):
    """O que cada papel pode fazer. O ADMIN pode conceder e remover."""

    __tablename__ = "papeis_permissoes"
    __table_args__ = (
        CheckConstraint(
            f"role IN ({_PAPEIS_SQL})",
            name="ck_papeis_permissoes_role_valido",
        ),
    )

    role: Mapped[str] = mapped_column(String(20), primary_key=True)
    permissao: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("autorizacao.permissoes.codigo", ondelete="CASCADE"),
        primary_key=True,
    )
    concedido_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditoriaRbac(Base):
    """Histórico de mudanças de permissões e papéis. Sem tokens nem dados pessoais."""

    __tablename__ = "auditoria_rbac"
    __table_args__ = (
        CheckConstraint(
            "acao IN (" + ", ".join(f"'{acao}'" for acao in ACOES_AUDITORIA) + ")",
            name="ck_auditoria_rbac_acao_valida",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ocorrido_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # conta_id do ADMIN que fez a mudança, ou "servico:perfis" para chamadas internas.
    ator: Mapped[str] = mapped_column(String(160), nullable=False)
    acao: Mapped[str] = mapped_column(String(40), nullable=False)
    papel: Mapped[str | None] = mapped_column(String(20))
    permissao: Mapped[str | None] = mapped_column(String(80))
    conta_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
