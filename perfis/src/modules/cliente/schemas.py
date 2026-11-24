from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.core.validators import cpf_valido, limpar_documento
from src.modules.perfil_usuario.perfil import StatusConta


class ClienteCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=150)
    cpf: str
    email: EmailStr
    senha: str = Field(min_length=6, max_length=30)
    telefone: str = Field(min_length=8, max_length=20)

    @field_validator("cpf")
    @classmethod
    def validar_cpf(cls, valor: str) -> str:
        cpf = limpar_documento(valor)
        if not cpf_valido(cpf):
            raise ValueError("CPF inválido")
        return cpf


class ClienteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    cpf_cnpj: str
    email: EmailStr
    telefone: str
    status: StatusConta
    criado_em: datetime
    atualizado_em: datetime
