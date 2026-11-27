"""torna categoria de cadastro da loja opcional

Revision ID: a7c3d91e5f20
Revises: f6c2a8d4e1b7
Create Date: 2026-11-27 19:00:00.000000

A categoria comercial do restaurante é mantida pelo Catálogo; Perfis não
deve exigir esse dado para criar a conta da empresa.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "a7c3d91e5f20"
down_revision: Union[str, Sequence[str], None] = "f6c2a8d4e1b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("lojas", "categoria", nullable=True)


def downgrade() -> None:
    op.alter_column("lojas", "categoria", nullable=False)
