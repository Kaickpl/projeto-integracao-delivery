"""pedido mínimo da loja

Revision ID: b1e4c7d9a2f6
Revises: a7c2e5f1d8b3
Create Date: 2026-11-22 21:00:00.000000

Adiciona `lojas.valor_minimo_pedido`, em centavos. As lojas que já existem
ficam com 0 (sem pedido mínimo).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1e4c7d9a2f6'
down_revision: Union[str, Sequence[str], None] = 'a7c2e5f1d8b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'lojas',
        sa.Column(
            'valor_minimo_pedido', sa.Integer(), server_default=sa.text('0'), nullable=False
        ),
    )
    op.create_check_constraint(
        'ck_loja_valor_minimo_pedido_nao_negativo', 'lojas', 'valor_minimo_pedido >= 0'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_loja_valor_minimo_pedido_nao_negativo', 'lojas', type_='check')
    op.drop_column('lojas', 'valor_minimo_pedido')
