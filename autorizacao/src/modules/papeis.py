from uuid import UUID

from sqlalchemy import CheckConstraint, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class PapelConta(Base):
    __tablename__ = "papeis_conta"
    __table_args__ = (
        CheckConstraint(
            "role IN ('CLIENTE', 'LOJA', 'ENTREGADOR', 'ADMIN')",
            name="ck_papeis_conta_role_valido",
        ),
    )

    conta_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
