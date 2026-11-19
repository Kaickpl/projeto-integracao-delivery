"""atributos da loja

Revision ID: c5e921514ce0
Revises: ca501498bbb7
Create Date: 2026-11-17 19:00:00.000000

Adiciona à loja os dados do cadastro de restaurante: descrição, URL da
imagem, categoria, taxa de entrega (centavos), tempo estimado mín./máx.
(minutos) e status de funcionamento.

Lojas que já existem recebem a categoria OUTROS, porque a coluna é
obrigatória.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c5e921514ce0'
down_revision: Union[str, Sequence[str], None] = 'ca501498bbb7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


categoria_loja = postgresql.ENUM(
    'PIZZARIA', 'HAMBURGUERIA', 'LANCHONETE', 'JAPONESA', 'BRASILEIRA',
    'ITALIANA', 'ARABE', 'CHINESA', 'SAUDAVEL', 'DOCERIA', 'ACAITERIA',
    'PADARIA', 'BEBIDAS', 'OUTROS',
    name='categoria_loja',
)
status_funcionamento = postgresql.ENUM(
    'ABERTO', 'FECHADO', 'INDISPONIVEL',
    name='status_funcionamento',
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    categoria_loja.create(bind, checkfirst=True)
    status_funcionamento.create(bind, checkfirst=True)

    op.add_column('lojas', sa.Column('descricao', sa.String(length=500), nullable=True))
    op.add_column('lojas', sa.Column('url_imagem', sa.String(length=500), nullable=True))
    # O server_default só preenche as lojas que já existem; depois é removido.
    op.add_column(
        'lojas',
        sa.Column(
            'categoria',
            postgresql.ENUM(name='categoria_loja', create_type=False),
            server_default='OUTROS',
            nullable=False,
        ),
    )
    op.alter_column('lojas', 'categoria', server_default=None)
    op.add_column(
        'lojas',
        sa.Column('taxa_entrega', sa.Integer(), server_default=sa.text('0'), nullable=False),
    )
    op.add_column('lojas', sa.Column('tempo_estimado_min', sa.Integer(), nullable=True))
    op.add_column('lojas', sa.Column('tempo_estimado_max', sa.Integer(), nullable=True))
    op.add_column(
        'lojas',
        sa.Column(
            'status_funcionamento',
            postgresql.ENUM(name='status_funcionamento', create_type=False),
            server_default='FECHADO',
            nullable=False,
        ),
    )

    op.create_check_constraint(
        'ck_loja_taxa_entrega_nao_negativa', 'lojas', 'taxa_entrega >= 0'
    )
    op.create_check_constraint(
        'ck_loja_tempo_estimado_positivo',
        'lojas',
        'tempo_estimado_min > 0 AND tempo_estimado_max > 0',
    )
    op.create_check_constraint(
        'ck_loja_tempo_estimado_max_maior_que_min',
        'lojas',
        'tempo_estimado_max >= tempo_estimado_min',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_loja_tempo_estimado_max_maior_que_min', 'lojas', type_='check')
    op.drop_constraint('ck_loja_tempo_estimado_positivo', 'lojas', type_='check')
    op.drop_constraint('ck_loja_taxa_entrega_nao_negativa', 'lojas', type_='check')
    op.drop_column('lojas', 'status_funcionamento')
    op.drop_column('lojas', 'tempo_estimado_max')
    op.drop_column('lojas', 'tempo_estimado_min')
    op.drop_column('lojas', 'taxa_entrega')
    op.drop_column('lojas', 'categoria')
    op.drop_column('lojas', 'url_imagem')
    op.drop_column('lojas', 'descricao')

    bind = op.get_bind()
    status_funcionamento.drop(bind, checkfirst=True)
    categoria_loja.drop(bind, checkfirst=True)
