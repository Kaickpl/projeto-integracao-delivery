"""Schemas de endereço, usados por quem tem endereço (loja e, depois, cliente)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.validators import cep_valido, limpar_cep, uf_valida


def _validar_cep(v: str | None) -> str | None:
    if v is None:
        return None
    cep = limpar_cep(v)
    if not cep_valido(cep):
        raise ValueError("CEP deve ter 8 dígitos")
    return cep


def _validar_uf(v: str | None) -> str | None:
    if v is None:
        return None
    uf = v.strip().upper()
    if not uf_valida(uf):
        raise ValueError("UF inválida (use a sigla do estado, ex.: PE)")
    return uf


class EnderecoCreate(BaseModel):
    cep: str = Field(description="Com ou sem hífen")
    logradouro: str = Field(min_length=2, max_length=150)
    numero: str = Field(min_length=1, max_length=10)
    complemento: str | None = Field(default=None, max_length=100)
    bairro: str = Field(min_length=2, max_length=100)
    cidade: str = Field(min_length=2, max_length=100)
    uf: str = Field(description="Sigla do estado, ex.: PE")
    referencia: str | None = Field(default=None, max_length=150)

    @field_validator("cep")
    @classmethod
    def validar_cep(cls, v: str) -> str:
        return _validar_cep(v)

    @field_validator("uf")
    @classmethod
    def validar_uf(cls, v: str) -> str:
        return _validar_uf(v)


class EnderecoUpdate(BaseModel):
    """Só os campos enviados são alterados."""

    cep: str | None = None
    logradouro: str | None = Field(default=None, min_length=2, max_length=150)
    numero: str | None = Field(default=None, min_length=1, max_length=10)
    # Podem ser enviados como null para apagar.
    complemento: str | None = Field(default=None, max_length=100)
    bairro: str | None = Field(default=None, min_length=2, max_length=100)
    cidade: str | None = Field(default=None, min_length=2, max_length=100)
    uf: str | None = None
    referencia: str | None = Field(default=None, max_length=150)

    @field_validator("cep", "logradouro", "numero", "bairro", "cidade", "uf")
    @classmethod
    def nao_pode_ser_nulo(cls, v):
        # Só roda para campos enviados: omitir pode, mandar null não.
        if v is None:
            raise ValueError("Não pode ser nulo")
        return v

    @field_validator("cep")
    @classmethod
    def validar_cep(cls, v: str | None) -> str | None:
        return _validar_cep(v)

    @field_validator("uf")
    @classmethod
    def validar_uf(cls, v: str | None) -> str | None:
        return _validar_uf(v)


class EnderecoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cep: str
    logradouro: str
    numero: str
    complemento: str | None
    bairro: str
    cidade: str
    uf: str
    referencia: str | None
