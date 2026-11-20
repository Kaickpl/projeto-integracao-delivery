import re
from datetime import datetime
from uuid import UUID

from src.core.validators import documento_valido, limpar_documento

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.modules.perfil_usuario.perfil import StatusConta, TipoPerfil



class AdminCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=150)
    cpf_cnpj: str
    email: EmailStr
    senha: str = Field(min_length=6, max_length=30)
    telefone: str = Field(min_length=8, max_length=20)

    @field_validator("cpf_cnpj")
    @classmethod
    def validar_documento(cls, v: str) -> str:
        documento = limpar_documento(v)
        if not documento_valido(documento):
            raise ValueError("CPF ou CNPJ inválido")
        return documento


class PerfilAdminUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=150)
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, min_length=8, max_length=20)


class StatusUpdate(BaseModel):
    status: StatusConta


class PerfilAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tipo: TipoPerfil
    nome: str
    cpf_cnpj: str
    email: EmailStr
    telefone: str
    status: StatusConta
    criado_em: datetime
    atualizado_em: datetime