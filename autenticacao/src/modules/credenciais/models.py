from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class Credencial(Base):
    __tablename__ = "credenciais"

    conta_id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    senha_hash: Mapped[str] = mapped_column(Text, deferred=True)
    falhas_login: Mapped[list[datetime]] = mapped_column(
        ARRAY(DateTime(timezone=True)), server_default="{}"
    )
    login_bloqueado_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("uq_credenciais_email", func.lower(email), unique=True),
    )
