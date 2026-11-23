"""horários de funcionamento

Revision ID: c8d2f5a1e7b4
Revises: b1e4c7d9a2f6
Create Date: 2026-11-22 21:05:00.000000

Cria a tabela `horarios_funcionamento` (um intervalo por linha: loja, dia
da semana, hora de abrir e de fechar) e o enum `dia_semana`.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c8d2f5a1e7b4'
down_revision: Union[str, Sequence[str], None] = 'b1e4c7d9a2f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


dia_semana = postgresql.ENUM(
    'SEGUNDA', 'TERCA', 'QUARTA', 'QUINTA', 'SEXTA', 'SABADO', 'DOMINGO',
    name='dia_semana',
)


def upgrade() -> None:
    """Upgrade schema."""
    dia_semana.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'horarios_funcionamento',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('loja_id', sa.UUID(), nullable=False),
        sa.Column(
            'dia_semana',
            postgresql.ENUM(name='dia_semana', create_type=False),
            nullable=False,
        ),
        sa.Column('abre', sa.Time(), nullable=False),
        sa.Column('fecha', sa.Time(), nullable=False),
        sa.CheckConstraint('abre <> fecha', name='ck_horario_abre_diferente_de_fecha'),
        sa.ForeignKeyConstraint(['loja_id'], ['lojas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'loja_id', 'dia_semana', 'abre', name='uq_horario_loja_dia_abre'
        ),
    )
    op.create_index(
        op.f('ix_horarios_funcionamento_loja_id'),
        'horarios_funcionamento',
        ['loja_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_horarios_funcionamento_loja_id'), table_name='horarios_funcionamento'
    )
    op.drop_table('horarios_funcionamento')
    dia_semana.drop(op.get_bind(), checkfirst=True)
