"""Cria a tabela de credenciais do Auth.

Revision ID: 9c124a8cfa01
"""
import sqlalchemy as sa
from alembic import op

revision = "9c124a8cfa01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credenciais",
        sa.Column("conta_id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("senha_hash", sa.Text(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="autenticacao",
    )
    op.create_index(
        "uq_credenciais_email",
        "credenciais",
        [sa.text("lower(email)")],
        unique=True,
        schema="autenticacao",
    )


def downgrade() -> None:
    op.drop_table("credenciais", schema="autenticacao")
