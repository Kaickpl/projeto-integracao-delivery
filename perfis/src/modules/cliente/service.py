from uuid import UUID

from sqlalchemy.orm import Session

from src.core.provisionamento import provisionar_cadastro
from src.modules.cliente.schemas import ClienteCreate
from src.modules.perfil_usuario.cliente import Cliente
from src.modules.perfil_usuario.perfil import StatusConta, TipoPerfil


def cadastrar_cliente(
    db: Session, dados: ClienteCreate, chave_idempotencia: UUID
) -> Cliente:
    cliente = Cliente(
        tipo=TipoPerfil.CLIENTE,
        nome=dados.nome,
        cpf_cnpj=dados.cpf,
        email=str(dados.email),
        telefone=dados.telefone,
        status=StatusConta.PENDENTE_APROVACAO,
    )
    return provisionar_cadastro(
        db,
        cliente,
        senha=dados.senha,
        role="CLIENTE",
        chave_idempotencia=chave_idempotencia,
        dados_cadastro=dados.model_dump(exclude={"senha"}),
    )
