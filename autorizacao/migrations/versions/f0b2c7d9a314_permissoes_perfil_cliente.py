"""Concede ao cliente permissões para gerir o próprio perfil."""
from alembic import op
import sqlalchemy as sa

revision = "f0b2c7d9a314"
down_revision = "e4b8c1d7f092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    permissao = sa.table(
        "papeis_permissoes",
        sa.column("role", sa.String(length=20)),
        sa.column("permissao", sa.String(length=80)),
        schema="autorizacao",
    )
    op.bulk_insert(
        permissao,
        [
            {"role": "CLIENTE", "permissao": "perfil:editar_proprio"},
            {"role": "CLIENTE", "permissao": "perfil:remover_proprio"},
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM autorizacao.papeis_permissoes "
        "WHERE role = 'CLIENTE' AND permissao IN "
        "('perfil:editar_proprio', 'perfil:remover_proprio')"
    )
