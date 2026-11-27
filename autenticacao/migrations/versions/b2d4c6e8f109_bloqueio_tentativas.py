"""Persiste a janela de falhas e o bloqueio de login de cada credencial."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "b2d4c6e8f109"
down_revision = "c5d7312a4e90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "credenciais",
        sa.Column(
            "falhas_login",
            ARRAY(sa.DateTime(timezone=True)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        schema="autenticacao",
    )
    op.add_column(
        "credenciais",
        sa.Column("login_bloqueado_ate", sa.DateTime(timezone=True)),
        schema="autenticacao",
    )


def downgrade() -> None:
    op.drop_column("credenciais", "login_bloqueado_ate", schema="autenticacao")
    op.drop_column("credenciais", "falhas_login", schema="autenticacao")
