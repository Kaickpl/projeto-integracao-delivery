"""endereco um para um com cliente e loja

Revision ID: e0eab9b0781d
Revises: 75217b8a3f4e
Create Date: 2026-11-19 15:00:00.000000

`enderecos` vira uma tabela própria, sem dono embutido, e quem aponta para ela
é o dono:

- `clientes.endereco_id` -> `enderecos.id` (opcional, único);
- `lojas.endereco_id` -> `enderecos.id` (obrigatório, único).

Cada cliente e cada loja têm no máximo um endereço, e um endereço pertence a
um dono só. Os campos de endereço que estavam em `lojas` voltam para
`enderecos`.

Saem de `enderecos`: `cliente_id`, `apelido` e `principal` (com um endereço
por cliente, não fazem mais sentido).

Se algum cliente tiver mais de um endereço, a migração para com uma mensagem,
sem mudar nada.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0eab9b0781d'
down_revision: Union[str, Sequence[str], None] = '75217b8a3f4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Campos de endereço que estavam em `lojas`: (nome, tamanho, obrigatório)
CAMPOS = [
    ('cep', 8, True),
    ('logradouro', 150, True),
    ('numero', 10, True),
    ('complemento', 100, False),
    ('bairro', 100, True),
    ('cidade', 100, True),
    ('uf', 2, True),
    ('referencia', 150, False),
]
NOMES = ', '.join(nome for nome, _, _ in CAMPOS)


def upgrade() -> None:
    """Upgrade schema."""
    com_varios = op.get_bind().execute(sa.text(
        """
        SELECT count(*) FROM (
            SELECT cliente_id FROM enderecos GROUP BY cliente_id HAVING count(*) > 1
        ) clientes_com_varios
        """
    )).scalar()
    if com_varios:
        raise RuntimeError(
            f"Existem clientes com mais de um endereço ({com_varios} encontrado(s)). "
            "Agora cada cliente tem no máximo um: apague os endereços extras "
            "antes de migrar."
        )

    # 1. Cliente passa a apontar para o próprio endereço.
    op.add_column('clientes', sa.Column('endereco_id', sa.UUID(), nullable=True))
    op.execute(
        "UPDATE clientes c SET endereco_id = e.id FROM enderecos e WHERE e.cliente_id = c.id"
    )

    # 2. `enderecos` deixa de guardar o dono.
    op.drop_constraint('enderecos_cliente_id_fkey', 'enderecos', type_='foreignkey')
    op.drop_index(
        'uq_endereco_principal_por_cliente',
        table_name='enderecos',
        postgresql_where=sa.text('principal'),
    )
    op.drop_index('ix_enderecos_cliente_id', table_name='enderecos')
    op.drop_column('enderecos', 'cliente_id')
    op.drop_column('enderecos', 'apelido')
    op.drop_column('enderecos', 'principal')

    # 3. O endereço de cada loja sai das colunas de `lojas` e vira uma linha em
    #    `enderecos`, ligada por `lojas.endereco_id`.
    op.add_column('lojas', sa.Column('endereco_id', sa.UUID(), nullable=True))
    op.execute("UPDATE lojas SET endereco_id = gen_random_uuid()")
    op.execute(
        f"INSERT INTO enderecos (id, {NOMES}) SELECT endereco_id, {NOMES} FROM lojas"
    )
    op.alter_column('lojas', 'endereco_id', nullable=False)
    op.drop_constraint('ck_loja_uf_sigla', 'lojas', type_='check')
    op.drop_constraint('ck_loja_cep_8_digitos', 'lojas', type_='check')
    for nome, _, _ in reversed(CAMPOS):
        op.drop_column('lojas', nome)

    # 4. Chaves estrangeiras e unicidade (um endereço, um dono).
    op.create_unique_constraint('uq_clientes_endereco_id', 'clientes', ['endereco_id'])
    op.create_unique_constraint('uq_lojas_endereco_id', 'lojas', ['endereco_id'])
    op.create_foreign_key(
        'fk_clientes_endereco', 'clientes', 'enderecos',
        ['endereco_id'], ['id'], ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_lojas_endereco', 'lojas', 'enderecos',
        ['endereco_id'], ['id'], ondelete='RESTRICT',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_lojas_endereco', 'lojas', type_='foreignkey')
    op.drop_constraint('fk_clientes_endereco', 'clientes', type_='foreignkey')
    op.drop_constraint('uq_lojas_endereco_id', 'lojas', type_='unique')
    op.drop_constraint('uq_clientes_endereco_id', 'clientes', type_='unique')

    # 3. Endereço da loja volta para colunas de `lojas`.
    for nome, tamanho, _ in CAMPOS:
        op.add_column('lojas', sa.Column(nome, sa.String(length=tamanho), nullable=True))
    atribuicoes = ', '.join(f'{nome} = e.{nome}' for nome, _, _ in CAMPOS)
    op.execute(f"UPDATE lojas l SET {atribuicoes} FROM enderecos e WHERE e.id = l.endereco_id")
    for nome, _, obrigatorio in CAMPOS:
        if obrigatorio:
            op.alter_column('lojas', nome, nullable=False)
    op.create_check_constraint('ck_loja_cep_8_digitos', 'lojas', "cep ~ '^[0-9]{8}$'")
    op.create_check_constraint('ck_loja_uf_sigla', 'lojas', "uf ~ '^[A-Z]{2}$'")
    op.execute("DELETE FROM enderecos WHERE id IN (SELECT endereco_id FROM lojas)")
    op.drop_column('lojas', 'endereco_id')

    # 2. `enderecos` volta a guardar o cliente dono.
    op.add_column(
        'enderecos',
        sa.Column('principal', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.add_column('enderecos', sa.Column('apelido', sa.String(length=50), nullable=True))
    op.add_column('enderecos', sa.Column('cliente_id', sa.UUID(), nullable=True))
    op.execute(
        "UPDATE enderecos e SET cliente_id = c.id, principal = true "
        "FROM clientes c WHERE c.endereco_id = e.id"
    )
    # Endereços sem dono não cabem na estrutura antiga.
    op.execute("DELETE FROM enderecos WHERE cliente_id IS NULL")
    op.alter_column('enderecos', 'cliente_id', nullable=False)
    op.create_index('ix_enderecos_cliente_id', 'enderecos', ['cliente_id'], unique=False)
    op.create_index(
        'uq_endereco_principal_por_cliente',
        'enderecos',
        ['cliente_id'],
        unique=True,
        postgresql_where=sa.text('principal'),
    )
    op.create_foreign_key(
        'enderecos_cliente_id_fkey', 'enderecos', 'clientes',
        ['cliente_id'], ['id'], ondelete='CASCADE',
    )

    # 1.
    op.drop_column('clientes', 'endereco_id')
