"""Persiste idempotência e estado do provisionamento de identidade."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c1a7e9d4b602"
down_revision = "f6c2a8d4e1b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "perfis",
        sa.Column(
            "identidade_pronta",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.add_column(
        "perfis",
        sa.Column("chave_idempotencia", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "perfis", sa.Column("dados_cadastro_hash", sa.String(length=64), nullable=True)
    )
    op.create_index(
        "uq_perfis_chave_idempotencia",
        "perfis",
        ["chave_idempotencia"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_perfis_chave_idempotencia", table_name="perfis")
    op.drop_column("perfis", "dados_cadastro_hash")
    op.drop_column("perfis", "chave_idempotencia")
    op.drop_column("perfis", "identidade_pronta")
