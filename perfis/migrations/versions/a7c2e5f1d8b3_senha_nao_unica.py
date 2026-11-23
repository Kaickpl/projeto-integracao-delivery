"""senha não é única

Revision ID: a7c2e5f1d8b3
Revises: d3f1a7c4b2e9
Create Date: 2026-11-22 10:00:00.000000

Remove o índice único de `perfis.senha`. Com ele, um segundo cadastro com
uma senha já usada por outra pessoa era recusado (e a resposta dizia que o
CPF/CNPJ ou e-mail estava repetido).

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a7c2e5f1d8b3'
down_revision: Union[str, Sequence[str], None] = 'd3f1a7c4b2e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index('ix_perfis_senha', table_name='perfis')


def downgrade() -> None:
    """Downgrade schema."""
    # Falha se já houver senhas repetidas.
    op.create_index('ix_perfis_senha', 'perfis', ['senha'], unique=True)
