"""Cria o cadastro de clientes OAuth de serviço.

Revision ID: c5d7312a4e90
Revises: 7f29b05c18de
"""
import sqlalchemy as sa
from alembic import op

revision = "c5d7312a4e90"
down_revision = "7f29b05c18de"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clientes_servico",
        sa.Column("client_id", sa.String(length=120), primary_key=True),
        sa.Column("segredo_hash", sa.Text(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("segredo_atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="autenticacao",
    )


def downgrade() -> None:
    op.drop_table("clientes_servico", schema="autenticacao")
