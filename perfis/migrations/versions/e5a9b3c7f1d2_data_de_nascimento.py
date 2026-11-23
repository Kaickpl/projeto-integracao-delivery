"""data de nascimento

Revision ID: e5a9b3c7f1d2
Revises: c8d2f5a1e7b4
Create Date: 2026-11-23 10:00:00.000000

Adiciona `perfis.data_nascimento`. Cadastro novo de cliente, entregador e
admin exige a data (e 18 anos ou mais). A coluna aceita vazio porque loja
não tem data de nascimento e para não quebrar os perfis que já existem: o
admin preenche esses pelo PATCH /admin/perfis/{id}.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a9b3c7f1d2'
down_revision: Union[str, Sequence[str], None] = 'c8d2f5a1e7b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('perfis', sa.Column('data_nascimento', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('perfis', 'data_nascimento')
