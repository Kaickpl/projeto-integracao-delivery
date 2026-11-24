"""Cria códigos de autorização OAuth de uso único.

Revision ID: 7f29b05c18de
Revises: 3a6f2c9d1e40
"""
import sqlalchemy as sa
from alembic import op

revision = "7f29b05c18de"
down_revision = "3a6f2c9d1e40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "codigos_autorizacao",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("codigo_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("conta_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.String(120), nullable=False),
        sa.Column("redirect_uri", sa.String(500), nullable=False),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True)),
        schema="autenticacao",
    )


def downgrade() -> None:
    op.drop_table("codigos_autorizacao", schema="autenticacao")
