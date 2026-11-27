from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.core.validators import cpf_valido, limpar_documento
from src.modules.endereco.schemas import EnderecoCreate, EnderecoResponse
from src.modules.perfil_usuario.perfil import StatusConta


class ClienteCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=150)
    cpf: str
    email: EmailStr
    senha: str = Field(min_length=6, max_length=30)
    telefone: str = Field(min_length=8, max_length=20)
    endereco: EnderecoCreate | None = None

    @field_validator("cpf")
    @classmethod
    def validar_cpf(cls, valor: str) -> str:
        cpf = limpar_documento(valor)
        if not cpf_valido(cpf):
            raise ValueError("CPF inválido")
        return cpf


class ClienteUpdate(BaseModel):
    """Campos editáveis pelo cliente; endereço é substituído por completo ou removido.

    E-mail, CPF e status não são alterados por este endpoint.
    """

    nome: str | None = Field(default=None, min_length=2, max_length=150)
    telefone: str | None = Field(default=None, min_length=8, max_length=20)
    endereco: EnderecoCreate | None = None

    @field_validator("nome", "telefone")
    @classmethod
    def campos_nao_podem_ser_nulos(cls, valor):
        if valor is None:
            raise ValueError("Não pode ser nulo")
        return valor


class ClienteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    cpf_cnpj: str
    email: EmailStr
    telefone: str
    endereco: EnderecoResponse | None
    status: StatusConta
    criado_em: datetime
    atualizado_em: datetime
