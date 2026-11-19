
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '75217b8a3f4e'
down_revision: Union[str, Sequence[str], None] = 'c5e921514ce0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Colunas de endereço da loja: (nome, tamanho, obrigatória)
COLUNAS_ENDERECO_LOJA = [
    ('cep', 8, True),
    ('logradouro', 150, True),
    ('numero', 10, True),
    ('complemento', 100, False),
    ('bairro', 100, True),
    ('cidade', 100, True),
    ('uf', 2, True),
    ('referencia', 150, False),
]
NOMES = [nome for nome, _, _ in COLUNAS_ENDERECO_LOJA]


def upgrade() -> None:
    """Upgrade schema."""
    sem_endereco = op.get_bind().execute(sa.text(
        """
        SELECT count(*) FROM lojas l
        WHERE NOT EXISTS (SELECT 1 FROM enderecos e WHERE e.perfil_id = l.id)
        """
    )).scalar()
    if sem_endereco:
        raise RuntimeError(
            f"Existem lojas sem endereço ({sem_endereco} encontrada(s)). "
            "O endereço da loja passa a ser obrigatório: cadastre o endereço "
            "delas (ou apague-as) antes de migrar."
        )

    # 1. Tabela própria de clientes, com os clientes que já existem.
    op.create_table(
        'clientes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['id'], ['perfis.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute("INSERT INTO clientes (id) SELECT id FROM perfis WHERE tipo = 'CLIENTE'")

    # 2. Endereço da loja vai para colunas de `lojas`.
    for nome, tamanho, _ in COLUNAS_ENDERECO_LOJA:
        op.add_column('lojas', sa.Column(nome, sa.String(length=tamanho), nullable=True))
    op.execute(
        f"""
        UPDATE lojas l SET {', '.join(f'{n} = e.{n}' for n in NOMES)}
        FROM enderecos e WHERE e.perfil_id = l.id
        """
    )
    op.execute("DELETE FROM enderecos WHERE perfil_tipo = 'LOJA'")
    for nome, _, obrigatoria in COLUNAS_ENDERECO_LOJA:
        if obrigatoria:
            op.alter_column('lojas', nome, nullable=False)
    op.create_check_constraint('ck_loja_cep_8_digitos', 'lojas', "cep ~ '^[0-9]{8}$'")
    op.create_check_constraint('ck_loja_uf_sigla', 'lojas', "uf ~ '^[A-Z]{2}$'")

    # 3. `enderecos` passa a ser só de cliente, ligado direto a `clientes`.
    op.drop_index(
        'uq_endereco_unico_por_loja',
        table_name='enderecos',
        postgresql_where=sa.text("perfil_tipo = 'LOJA'"),
    )
    op.drop_constraint('ck_endereco_somente_cliente_ou_loja', 'enderecos', type_='check')
    op.drop_constraint('fk_enderecos_perfil', 'enderecos', type_='foreignkey')
    op.drop_column('enderecos', 'perfil_tipo')
    op.alter_column('enderecos', 'perfil_id', new_column_name='cliente_id')
    op.execute("ALTER INDEX ix_enderecos_perfil_id RENAME TO ix_enderecos_cliente_id")
    op.execute(
        "ALTER INDEX uq_endereco_principal_por_perfil RENAME TO uq_endereco_principal_por_cliente"
    )
    op.create_foreign_key(
        'enderecos_cliente_id_fkey',
        'enderecos', 'clientes',
        ['cliente_id'], ['id'],
        ondelete='CASCADE',
    )

    # 4. Não é mais usado por nenhuma FK.
    op.drop_constraint('uq_perfis_id_tipo', 'perfis', type_='unique')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_unique_constraint('uq_perfis_id_tipo', 'perfis', ['id', 'tipo'])

    # 3. Volta `enderecos` a apontar para `perfis` com o tipo copiado.
    op.drop_constraint('enderecos_cliente_id_fkey', 'enderecos', type_='foreignkey')
    op.execute(
        "ALTER INDEX uq_endereco_principal_por_cliente RENAME TO uq_endereco_principal_por_perfil"
    )
    op.execute("ALTER INDEX ix_enderecos_cliente_id RENAME TO ix_enderecos_perfil_id")
    op.alter_column('enderecos', 'cliente_id', new_column_name='perfil_id')
    op.add_column(
        'enderecos',
        sa.Column(
            'perfil_tipo',
            postgresql.ENUM(name='tipo_perfil', create_type=False),
            nullable=True,
        ),
    )
    op.execute("UPDATE enderecos SET perfil_tipo = 'CLIENTE'")

    # 2. Endereço da loja volta para `enderecos`.
    op.execute(
        f"""
        INSERT INTO enderecos (id, perfil_id, perfil_tipo, {', '.join(NOMES)})
        SELECT gen_random_uuid(), id, 'LOJA', {', '.join(NOMES)} FROM lojas
        """
    )
    op.alter_column('enderecos', 'perfil_tipo', nullable=False)
    op.create_foreign_key(
        'fk_enderecos_perfil',
        'enderecos', 'perfis',
        ['perfil_id', 'perfil_tipo'], ['id', 'tipo'],
        ondelete='CASCADE',
    )
    op.create_check_constraint(
        'ck_endereco_somente_cliente_ou_loja',
        'enderecos',
        "perfil_tipo IN ('CLIENTE', 'LOJA')",
    )
    op.create_index(
        'uq_endereco_unico_por_loja',
        'enderecos',
        ['perfil_id'],
        unique=True,
        postgresql_where=sa.text("perfil_tipo = 'LOJA'"),
    )
    op.drop_constraint('ck_loja_uf_sigla', 'lojas', type_='check')
    op.drop_constraint('ck_loja_cep_8_digitos', 'lojas', type_='check')
    for nome in reversed(NOMES):
        op.drop_column('lojas', nome)

    # 1. Clientes voltam a ficar só em `perfis`.
    op.drop_table('clientes')
