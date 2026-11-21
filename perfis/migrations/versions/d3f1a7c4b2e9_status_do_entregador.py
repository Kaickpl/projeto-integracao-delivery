"""status do entregador

Revision ID: d3f1a7c4b2e9
Revises: 58132cc7016e
Create Date: 2026-11-20 14:00:00.000000

Adiciona ao entregador a coluna `status_entregador` (DISPONIVEL, OCUPADO ou
INATIVO), que diz se ele está recebendo entregas agora. Entregadores que já
existem ficam INATIVO.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd3f1a7c4b2e9'
down_revision: Union[str, Sequence[str], None] = '58132cc7016e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


status_entregador = postgresql.ENUM(
    'DISPONIVEL', 'OCUPADO', 'INATIVO',
    name='status_entregador',
)


def upgrade() -> None:
    """Upgrade schema."""
    status_entregador.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'entregadores',
        sa.Column(
            'status_entregador',
            postgresql.ENUM(name='status_entregador', create_type=False),
            server_default='INATIVO',
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('entregadores', 'status_entregador')
    status_entregador.drop(op.get_bind(), checkfirst=True)
