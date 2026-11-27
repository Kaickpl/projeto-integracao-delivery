from datetime import datetime, time
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
from src.modules.perfil_usuario.horario_funcionamento import DiaSemana
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
    # Opcional no cadastro da conta; o Catálogo define a categoria do restaurante.
    categoria: CategoriaLoja | None = None
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
    categoria: CategoriaLoja | None
    taxa_entrega: int
    tempo_estimado_min: int | None
    tempo_estimado_max: int | None
    status_funcionamento: StatusFuncionamento
    endereco: EnderecoResponse
    criado_em: datetime
    atualizado_em: datetime


class LojaPublicaResponse(BaseModel):
    """O que qualquer pessoa vê na vitrine. Sem CNPJ, e-mail e telefone."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    status: StatusConta
    razao_social: str
    descricao: str | None
    url_imagem: str | None
    categoria: CategoriaLoja | None
    taxa_entrega: int
    tempo_estimado_min: int | None
    tempo_estimado_max: int | None
    status_funcionamento: StatusFuncionamento
    endereco: EnderecoResponse
    criado_em: datetime
    atualizado_em: datetime


class Horario(BaseModel):
    """Um intervalo de funcionamento, no horário local da loja."""

    model_config = ConfigDict(from_attributes=True)

    dia_semana: DiaSemana
    abre: time = Field(description="Ex.: 18:00")
    fecha: time = Field(
        description="Ex.: 23:00. Se for menor que `abre`, passa da meia-noite"
    )

    @model_validator(mode="after")
    def validar_intervalo(self):
        if self.abre == self.fecha:
            raise ValueError("O horário de abrir e o de fechar não podem ser iguais")
        return self


def _fim_no_mesmo_dia(horario: Horario) -> time | None:
    # Intervalo que passa da meia-noite vai até o fim do dia (None = 24:00).
    return horario.fecha if horario.fecha > horario.abre else None


class HorariosUpdate(BaseModel):
    """Substitui todos os horários da loja. Lista vazia apaga todos."""

    horarios: list[Horario] = Field(max_length=50)

    @model_validator(mode="after")
    def validar_sobreposicao(self):
        for dia in DiaSemana:
            do_dia = sorted(
                (h for h in self.horarios if h.dia_semana == dia), key=lambda h: h.abre
            )
            for anterior, seguinte in zip(do_dia, do_dia[1:]):
                fim = _fim_no_mesmo_dia(anterior)
                if fim is None or seguinte.abre < fim:
                    raise ValueError(f"Há horários sobrepostos em {dia.value}")
        return self
