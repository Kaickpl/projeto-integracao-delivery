"""Cria o catálogo de permissões, as permissões por papel e a auditoria do RBAC.

Revision ID: e4b8c1d7f092
Revises: d8f1c9a20b34
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e4b8c1d7f092"
down_revision = "d8f1c9a20b34"
branch_labels = None
depends_on = None

SCHEMA = "autorizacao"
PAPEIS_SQL = "'CLIENTE', 'LOJA', 'ENTREGADOR', 'ADMIN'"
ACOES_SQL = "'PERMISSAO_CONCEDIDA', 'PERMISSAO_REMOVIDA', 'PAPEL_ASSOCIADO', 'PAPEL_REMOVIDO'"

CATALOGO = [
    ("perfis:listar", "Listar e consultar qualquer perfil na área administrativa"),
    ("perfis:editar_qualquer", "Editar os dados de qualquer perfil"),
    ("perfis:alterar_status", "Aprovar, suspender ou reativar contas"),
    ("perfis:remover_qualquer", "Remover qualquer perfil"),
    ("admins:criar", "Cadastrar novos administradores"),
    ("perfil:ler_proprio", "Consultar os dados completos do próprio perfil"),
    ("perfil:editar_proprio", "Editar o próprio perfil"),
    ("perfil:remover_proprio", "Remover a própria conta"),
    ("loja:operar", "Abrir e fechar a própria loja"),
    ("entregador:operar", "Alterar a própria disponibilidade de entregador"),
    ("entregadores:listar", "Listar e consultar entregadores"),
    ("rbac:gerenciar", "Gerir as permissões dos papéis e consultar a auditoria"),
]

CONCESSOES = {
    "ADMIN": [
        "perfis:listar",
        "perfis:editar_qualquer",
        "perfis:alterar_status",
        "perfis:remover_qualquer",
        "admins:criar",
        "entregadores:listar",
        "rbac:gerenciar",
    ],
    "LOJA": [
        "perfil:ler_proprio",
        "perfil:editar_proprio",
        "perfil:remover_proprio",
        "loja:operar",
    ],
    "ENTREGADOR": [
        "perfil:ler_proprio",
        "perfil:editar_proprio",
        "perfil:remover_proprio",
        "entregador:operar",
    ],
    # O cliente ainda não tem rotas próprias de edição ou remoção.
    "CLIENTE": ["perfil:ler_proprio"],
}


def upgrade() -> None:
    permissoes = op.create_table(
        "permissoes",
        sa.Column("codigo", sa.String(length=80), primary_key=True),
        sa.Column("descricao", sa.String(length=255), nullable=False),
        schema=SCHEMA,
    )
    papeis_permissoes = op.create_table(
        "papeis_permissoes",
        sa.Column("role", sa.String(length=20), primary_key=True),
        sa.Column(
            "permissao",
            sa.String(length=80),
            sa.ForeignKey(f"{SCHEMA}.permissoes.codigo", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "concedido_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"role IN ({PAPEIS_SQL})", name="ck_papeis_permissoes_role_valido"
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "auditoria_rbac",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "ocorrido_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ator", sa.String(length=160), nullable=False),
        sa.Column("acao", sa.String(length=40), nullable=False),
        sa.Column("papel", sa.String(length=20), nullable=True),
        sa.Column("permissao", sa.String(length=80), nullable=True),
        sa.Column("conta_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(f"acao IN ({ACOES_SQL})", name="ck_auditoria_rbac_acao_valida"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_auditoria_rbac_ocorrido_em", "auditoria_rbac", ["ocorrido_em"], schema=SCHEMA
    )
    op.create_index(
        "ix_auditoria_rbac_conta_id", "auditoria_rbac", ["conta_id"], schema=SCHEMA
    )

    op.bulk_insert(
        permissoes,
        [{"codigo": codigo, "descricao": descricao} for codigo, descricao in CATALOGO],
    )
    op.bulk_insert(
        papeis_permissoes,
        [
            {"role": papel, "permissao": permissao}
            for papel, lista in CONCESSOES.items()
            for permissao in lista
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_auditoria_rbac_conta_id", table_name="auditoria_rbac", schema=SCHEMA)
    op.drop_index("ix_auditoria_rbac_ocorrido_em", table_name="auditoria_rbac", schema=SCHEMA)
    op.drop_table("auditoria_rbac", schema=SCHEMA)
    op.drop_table("papeis_permissoes", schema=SCHEMA)
    op.drop_table("permissoes", schema=SCHEMA)
