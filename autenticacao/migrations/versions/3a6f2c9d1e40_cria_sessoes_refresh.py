"""Cria armazenamento compartilhado de refresh tokens.

Revision ID: 3a6f2c9d1e40
Revises: 9c124a8cfa01
"""
import sqlalchemy as sa
from alembic import op

revision = "3a6f2c9d1e40"
down_revision = "9c124a8cfa01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessoes_refresh",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sessao_id", sa.Uuid(), nullable=False),
        sa.Column("conta_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("client_id", sa.String(120), nullable=False),
        sa.Column("audiencia", sa.String(255), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revogado_em", sa.DateTime(timezone=True)),
        sa.Column("substituido_por_id", sa.Uuid(), sa.ForeignKey("autenticacao.sessoes_refresh.id")),
        schema="autenticacao",
    )
    op.create_index("ix_sessoes_refresh_sessao", "sessoes_refresh", ["sessao_id"], schema="autenticacao")


def downgrade() -> None:
    op.drop_table("sessoes_refresh", schema="autenticacao")
