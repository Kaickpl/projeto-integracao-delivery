
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '87c94cc0117d'
down_revision: Union[str, Sequence[str], None] = 'e0eab9b0781d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'admins',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['id'], ['perfis.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute("INSERT INTO admins (id) SELECT id FROM perfis WHERE tipo = 'ADMIN'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('admins')
