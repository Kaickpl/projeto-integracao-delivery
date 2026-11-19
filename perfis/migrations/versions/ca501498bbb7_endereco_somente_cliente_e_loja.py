"""endereco somente para cliente e loja

Revision ID: ca501498bbb7
Revises: b5d479aa5384
Create Date: 2026-11-17 18:00:00.000000

Garante no banco que só Cliente (vários endereços) e Loja (um endereço) têm
endereço. Entregador e Admin não têm.

- `enderecos.perfil_tipo` guarda o tipo do perfil dono do endereço;
- a FK composta (perfil_id, perfil_tipo) -> perfis (id, tipo) impede que esse
  tipo fique diferente do tipo real do perfil;
- um CHECK aceita só CLIENTE e LOJA;
- um índice único parcial deixa no máximo um endereço por loja.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ca501498bbb7'
down_revision: Union[str, Sequence[str], None] = 'b5d479aa5384'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _falhar_se_houver(sql: str, mensagem: str) -> None:
    quantidade = op.get_bind().execute(sa.text(sql)).scalar()
    if quantidade:
        raise RuntimeError(f"{mensagem} ({quantidade} encontrado(s)). Corrija os dados antes de migrar.")


def upgrade() -> None:
    """Upgrade schema."""
    # Não apagamos dados automaticamente: se houver endereço que viola a nova
    # regra, a migração para e avisa.
    _falhar_se_houver(
        """
        SELECT count(*) FROM enderecos e JOIN perfis p ON p.id = e.perfil_id
        WHERE p.tipo NOT IN ('CLIENTE', 'LOJA')
        """,
        "Existem endereços de Entregador ou Admin",
    )
    _falhar_se_houver(
        """
        SELECT count(*) FROM (
            SELECT e.perfil_id FROM enderecos e JOIN perfis p ON p.id = e.perfil_id
            WHERE p.tipo = 'LOJA' GROUP BY e.perfil_id HAVING count(*) > 1
        ) lojas_com_varios
        """,
        "Existem lojas com mais de um endereço",
    )

    op.create_unique_constraint('uq_perfis_id_tipo', 'perfis', ['id', 'tipo'])

    op.add_column(
        'enderecos',
        sa.Column(
            'perfil_tipo',
            postgresql.ENUM(name='tipo_perfil', create_type=False),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE enderecos e SET perfil_tipo = p.tipo FROM perfis p WHERE p.id = e.perfil_id"
    )
    op.alter_column('enderecos', 'perfil_tipo', nullable=False)

    op.drop_constraint('enderecos_perfil_id_fkey', 'enderecos', type_='foreignkey')
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


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'uq_endereco_unico_por_loja',
        table_name='enderecos',
        postgresql_where=sa.text("perfil_tipo = 'LOJA'"),
    )
    op.drop_constraint('ck_endereco_somente_cliente_ou_loja', 'enderecos', type_='check')
    op.drop_constraint('fk_enderecos_perfil', 'enderecos', type_='foreignkey')
    op.create_foreign_key(
        'enderecos_perfil_id_fkey',
        'enderecos', 'perfis',
        ['perfil_id'], ['id'],
        ondelete='CASCADE',
    )
    op.drop_column('enderecos', 'perfil_tipo')
    op.drop_constraint('uq_perfis_id_tipo', 'perfis', type_='unique')
