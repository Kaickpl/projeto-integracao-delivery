from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from src.core.validators import (
    cnh_valida,
    cpf_valido,
    limpar_documento,
    limpar_placa,
    placa_valida,
)
from src.modules.perfil_usuario.entregador import StatusEntregador, TipoVeiculo
from src.modules.perfil_usuario.perfil import StatusConta

MENSAGEM_VEICULO_SEM_DOCUMENTOS = "Moto e carro exigem placa e CNH"


def faltam_documentos_do_veiculo(
    tipo_veiculo: TipoVeiculo, placa: str | None, cnh: str | None
) -> bool:
    """Mesma regra do banco: só bicicleta pode ficar sem placa e CNH."""
    return tipo_veiculo != TipoVeiculo.BICICLETA and (placa is None or cnh is None)


def _validar_placa(v: str | None) -> str | None:
    if v is None:
        return None
    placa = limpar_placa(v)
    if not placa_valida(placa):
        raise ValueError("Placa inválida (use ABC1234 ou ABC1D23)")
    return placa


def _validar_cnh(v: str | None) -> str | None:
    if v is None:
        return None
    cnh = limpar_documento(v)
    if not cnh_valida(cnh):
        raise ValueError("CNH deve ter 11 dígitos")
    return cnh


class EntregadorCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=150)
    cpf_cnpj: str
    email: EmailStr
    senha: str = Field(min_length=6, max_length=30)
    telefone: str = Field(min_length=8, max_length=20)
    tipo_veiculo: TipoVeiculo
    placa: str | None = None
    cnh: str | None = None

    @field_validator("cpf_cnpj")
    @classmethod
    def validar_cpf(cls, v: str) -> str:
        # Entregador é pessoa física: só aceita CPF.
        cpf = limpar_documento(v)
        if not cpf_valido(cpf):
            raise ValueError("CPF inválido")
        return cpf

    @field_validator("placa")
    @classmethod
    def validar_placa(cls, v: str | None) -> str | None:
        return _validar_placa(v)

    @field_validator("cnh")
    @classmethod
    def validar_cnh(cls, v: str | None) -> str | None:
        return _validar_cnh(v)

    @model_validator(mode="after")
    def validar_veiculo(self):
        if faltam_documentos_do_veiculo(self.tipo_veiculo, self.placa, self.cnh):
            raise ValueError(MENSAGEM_VEICULO_SEM_DOCUMENTOS)
        return self


class EntregadorUpdate(BaseModel):
    """Edição do perfil. Só os campos enviados são alterados.

    CPF, senha e os status não mudam por aqui.
    """

    nome: str | None = Field(default=None, min_length=2, max_length=150)
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, min_length=8, max_length=20)
    tipo_veiculo: TipoVeiculo | None = None
    # Podem ser enviados como null para apagar (só se o veículo for bicicleta).
    placa: str | None = None
    cnh: str | None = None

    @field_validator("nome", "email", "telefone", "tipo_veiculo")
    @classmethod
    def nao_pode_ser_nulo(cls, v):
        # Só roda para campos enviados: omitir pode, mandar null não.
        if v is None:
            raise ValueError("Não pode ser nulo")
        return v

    @field_validator("placa")
    @classmethod
    def validar_placa(cls, v: str | None) -> str | None:
        return _validar_placa(v)

    @field_validator("cnh")
    @classmethod
    def validar_cnh(cls, v: str | None) -> str | None:
        return _validar_cnh(v)


class StatusEntregadorUpdate(BaseModel):
    status_entregador: StatusEntregador


class EntregadorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    cpf_cnpj: str
    email: EmailStr
    telefone: str
    status: StatusConta
    tipo_veiculo: TipoVeiculo
    placa: str | None
    cnh: str | None
    status_entregador: StatusEntregador
    criado_em: datetime
    atualizado_em: datetime
