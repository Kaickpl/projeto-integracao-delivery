"""Une as migrações de categoria opcional e provisionamento recuperável.

Revision ID: 482553a767b8

As duas partiam de f6c2a8d4e1b7 e deixavam duas pontas, o que fazia
`alembic upgrade head` falhar. Esta junção não altera o banco.
"""

revision = "482553a767b8"
down_revision = ("a7c3d91e5f20", "c1a7e9d4b602")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
