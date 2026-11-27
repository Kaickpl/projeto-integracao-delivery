from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.core.database import salvar_alteracoes
from src.core.exceptions import PerfilNaoEncontrado
from src.core.provisionamento import provisionar_cadastro, remover_cadastro
from src.modules.cliente.schemas import ClienteCreate, ClienteUpdate
from src.modules.perfil_usuario.cliente import Cliente
from src.modules.perfil_usuario.endereco import Endereco
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
        endereco=Endereco(**dados.endereco.model_dump()) if dados.endereco else None,
    )
    return provisionar_cadastro(
        db,
        cliente,
        senha=dados.senha,
        role="CLIENTE",
        chave_idempotencia=chave_idempotencia,
        dados_cadastro=dados.model_dump(exclude={"senha"}),
    )


def buscar_cliente(db: Session, cliente_id: UUID) -> Cliente:
    cliente = db.scalar(
        select(Cliente)
        .options(selectinload(Cliente.endereco))
        .where(Cliente.id == cliente_id)
    )
    if cliente is None:
        raise PerfilNaoEncontrado("Cliente não encontrado")
    return cliente


def atualizar_cliente(db: Session, cliente_id: UUID, dados: ClienteUpdate) -> Cliente:
    cliente = buscar_cliente(db, cliente_id)
    alteracoes = dados.model_dump(exclude_unset=True)
    if not alteracoes:
        return cliente

    endereco_enviado = "endereco" in alteracoes
    endereco = alteracoes.pop("endereco", None)
    for campo, valor in alteracoes.items():
        setattr(cliente, campo, valor)

    if endereco_enviado:
        cliente.endereco = Endereco(**endereco) if endereco is not None else None

    salvar_alteracoes(db)
    db.refresh(cliente)
    return cliente


def remover_cliente(db: Session, cliente_id: UUID) -> None:
    cliente = buscar_cliente(db, cliente_id)
    remover_cadastro(
        db,
        cliente,
        "Não foi possível excluir a conta: existem dados vinculados a este cliente",
    )
