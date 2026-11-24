"""Cria a fonte autoritativa de escopos e audiências M2M.

Revision ID: d8f1c9a20b34
Revises: a41e9cb72d60
"""
import sqlalchemy as sa
from alembic import op

revision = "d8f1c9a20b34"
down_revision = "a41e9cb72d60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "permissoes_clientes_servico",
        sa.Column("client_id", sa.String(length=120), primary_key=True),
        sa.Column("audiencia", sa.String(length=500), primary_key=True),
        sa.Column("escopo", sa.String(length=120), primary_key=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="autorizacao",
    )


def downgrade() -> None:
    op.drop_table("permissoes_clientes_servico", schema="autorizacao")
