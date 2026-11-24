"""Cria a associação autoritativa de conta e papel no RBAC.

Revision ID: a41e9cb72d60
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a41e9cb72d60"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "papeis_conta",
        sa.Column("conta_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "role IN ('CLIENTE', 'LOJA', 'ENTREGADOR', 'ADMIN')",
            name="ck_papeis_conta_role_valido",
        ),
        schema="autorizacao",
    )


def downgrade() -> None:
    op.drop_table("papeis_conta", schema="autorizacao")
