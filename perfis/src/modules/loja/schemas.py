from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from src.core.validators import cnpj_valido, limpar_documento
from src.modules.endereco.schemas import (
    EnderecoCreate,
    EnderecoResponse,
    EnderecoUpdate,
)
from src.modules.perfil_usuario.loja import CategoriaLoja, StatusFuncionamento
from src.modules.perfil_usuario.perfil import StatusConta

MENSAGEM_TEMPO_ESTIMADO = "O tempo estimado máximo não pode ser menor que o mínimo"

_URL = TypeAdapter(HttpUrl)


def tempo_estimado_invalido(minimo: int | None, maximo: int | None) -> bool:
    """Mesma regra do banco: com os dois preenchidos, o máximo não pode ser menor."""
    return minimo is not None and maximo is not None and maximo < minimo


def _validar_url(v: str | None) -> str | None:
    if v is None:
        return None
    try:
        _URL.validate_python(v)
    except ValidationError:
        raise ValueError("URL inválida (use um endereço http:// ou https://)")
    return v


class LojaCreate(BaseModel):
    nome: str = Field(
        min_length=2, max_length=150, description="Nome fantasia, o que o cliente vê"
    )
    cpf_cnpj: str = Field(description="CNPJ da loja, com ou sem pontuação")
    email: EmailStr
    senha: str = Field(min_length=6, max_length=30)
    telefone: str = Field(min_length=8, max_length=20)
    razao_social: str = Field(min_length=2, max_length=150)
    descricao: str | None = Field(default=None, max_length=500)
    url_imagem: str | None = Field(default=None, max_length=500)
    categoria: CategoriaLoja
    taxa_entrega: int = Field(default=0, ge=0, description="Em centavos (R$ 5,90 -> 590)")
    tempo_estimado_min: int | None = Field(default=None, gt=0, description="Em minutos")
    tempo_estimado_max: int | None = Field(default=None, gt=0, description="Em minutos")
    endereco: EnderecoCreate

    @field_validator("cpf_cnpj")
    @classmethod
    def validar_cnpj(cls, v: str) -> str:
        # Loja é pessoa jurídica (tem razão social): só aceita CNPJ.
        cnpj = limpar_documento(v)
        if not cnpj_valido(cnpj):
            raise ValueError("CNPJ inválido")
        return cnpj

    @field_validator("url_imagem")
    @classmethod
    def validar_url_imagem(cls, v: str | None) -> str | None:
        return _validar_url(v)

    @model_validator(mode="after")
    def validar_tempo_estimado(self):
        if tempo_estimado_invalido(self.tempo_estimado_min, self.tempo_estimado_max):
            raise ValueError(MENSAGEM_TEMPO_ESTIMADO)
        return self


class LojaPerfilUpdate(BaseModel):
    """Edição do perfil (dados da conta). Só os campos enviados são alterados.

    CNPJ, senha e os status não mudam por aqui.
    """

    nome: str | None = Field(default=None, min_length=2, max_length=150)
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, min_length=8, max_length=20)
    razao_social: str | None = Field(default=None, min_length=2, max_length=150)

    @field_validator("nome", "email", "telefone", "razao_social")
    @classmethod
    def nao_pode_ser_nulo(cls, v):
        # Só roda para campos enviados: omitir pode, mandar null não.
        if v is None:
            raise ValueError("Não pode ser nulo")
        return v


class LojaInformacoesUpdate(BaseModel):
    """Edição das informações que o cliente vê. Só os campos enviados são alterados."""

    # Podem ser enviados como null para apagar.
    descricao: str | None = Field(default=None, max_length=500)
    url_imagem: str | None = Field(default=None, max_length=500)
    tempo_estimado_min: int | None = Field(default=None, gt=0, description="Em minutos")
    tempo_estimado_max: int | None = Field(default=None, gt=0, description="Em minutos")
    # Não podem ser null.
    categoria: CategoriaLoja | None = None
    taxa_entrega: int | None = Field(
        default=None, ge=0, description="Em centavos (R$ 5,90 -> 590)"
    )
    endereco: EnderecoUpdate | None = None

    @field_validator("categoria", "taxa_entrega", "endereco")
    @classmethod
    def nao_pode_ser_nulo(cls, v):
        if v is None:
            raise ValueError("Não pode ser nulo")
        return v

    @field_validator("url_imagem")
    @classmethod
    def validar_url_imagem(cls, v: str | None) -> str | None:
        return _validar_url(v)


class StatusFuncionamentoUpdate(BaseModel):
    status_funcionamento: StatusFuncionamento


class LojaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    cpf_cnpj: str
    email: EmailStr
    telefone: str
    status: StatusConta
    razao_social: str
    descricao: str | None
    url_imagem: str | None
    categoria: CategoriaLoja
    taxa_entrega: int
    tempo_estimado_min: int | None
    tempo_estimado_max: int | None
    status_funcionamento: StatusFuncionamento
    endereco: EnderecoResponse
    criado_em: datetime
    atualizado_em: datetime
