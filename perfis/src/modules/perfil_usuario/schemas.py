from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class PerfilLeituraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    email: EmailStr
