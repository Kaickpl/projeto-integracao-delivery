"""Remove armazenamento de senha em Perfis; Auth passa a ser a fonte única.

Revision ID: f2d6a9c1b840
Revises: d3f1a7c4b2e9
"""
from alembic import op

revision = "f2d6a9c1b840"
down_revision = "d3f1a7c4b2e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Uma migração paralela pode já ter removido o índice único. A remoção
    # da coluna também descarta qualquer índice remanescente no PostgreSQL.
    op.execute("DROP INDEX IF EXISTS ix_perfis_senha")
    op.drop_column("perfis", "senha")


def downgrade() -> None:
    # Não restaura credenciais legadas: não há senhas em texto claro para recuperar.
    raise RuntimeError("Downgrade não suportado: credenciais pertencem ao Auth")
