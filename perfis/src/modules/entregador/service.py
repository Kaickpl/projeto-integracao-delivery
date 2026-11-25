from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.database import salvar_alteracoes
from src.core.exceptions import (
    AcaoNaoPermitida,
    DadosInvalidos,
    PerfilNaoEncontrado,
)
from src.core.provisionamento import provisionar_cadastro
from src.modules.entregador.schemas import (
    MENSAGEM_VEICULO_SEM_DOCUMENTOS,
    EntregadorCreate,
    EntregadorUpdate,
    faltam_documentos_do_veiculo,
)
from src.modules.perfil_usuario.entregador import Entregador, StatusEntregador
from src.modules.perfil_usuario.perfil import StatusConta


def cadastrar_entregador(
    db: Session, dados: EntregadorCreate, chave_idempotencia: UUID
) -> Entregador:
    # A conta começa aguardando a aprovação do admin e o entregador começa
    # offline.
    entregador = Entregador(
        **dados.model_dump(exclude={"senha"}),
        status=StatusConta.PENDENTE_APROVACAO,
        status_entregador=StatusEntregador.INATIVO,
    )
    return provisionar_cadastro(
        db,
        entregador,
        senha=dados.senha,
        role="ENTREGADOR",
        chave_idempotencia=chave_idempotencia,
        dados_cadastro=dados.model_dump(exclude={"senha"}),
    )


def buscar_entregador(db: Session, entregador_id: UUID) -> Entregador:
    # Se o id for de outro tipo de perfil (cliente, loja...), volta None.
    entregador = db.get(Entregador, entregador_id)
    if entregador is None:
        raise PerfilNaoEncontrado("Entregador não encontrado")
    return entregador


def listar_entregadores(
    db: Session,
    status_entregador: StatusEntregador | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Entregador]:
    stmt = select(Entregador).order_by(Entregador.criado_em).offset(skip).limit(limit)
    if status_entregador:
        stmt = stmt.where(Entregador.status_entregador == status_entregador)
    return list(db.scalars(stmt))


def atualizar_entregador(
    db: Session, entregador_id: UUID, dados: EntregadorUpdate
) -> Entregador:
    entregador = buscar_entregador(db, entregador_id)
    alteracoes = dados.model_dump(exclude_unset=True)

    # Confere o veículo como ele vai ficar depois da alteração.
    if faltam_documentos_do_veiculo(
        alteracoes.get("tipo_veiculo", entregador.tipo_veiculo),
        alteracoes.get("placa", entregador.placa),
        alteracoes.get("cnh", entregador.cnh),
    ):
        raise DadosInvalidos(MENSAGEM_VEICULO_SEM_DOCUMENTOS)

    for campo, valor in alteracoes.items():
        setattr(entregador, campo, valor)
    salvar_alteracoes(db)
    db.refresh(entregador)
    return entregador


def alterar_status_entregador(
    db: Session, entregador_id: UUID, novo_status: StatusEntregador
) -> Entregador:
    entregador = buscar_entregador(db, entregador_id)
    # Conta pendente ou suspensa não pode receber entregas.
    if novo_status != StatusEntregador.INATIVO and entregador.status != StatusConta.ATIVO:
        raise AcaoNaoPermitida(
            "Só entregadores com a conta ativa podem ficar disponíveis ou ocupados"
        )
    entregador.status_entregador = novo_status
    salvar_alteracoes(db)
    db.refresh(entregador)
    return entregador


def remover_entregador(db: Session, entregador_id: UUID) -> None:
    entregador = buscar_entregador(db, entregador_id)
    if entregador.status_entregador == StatusEntregador.OCUPADO:
        raise AcaoNaoPermitida("Não é possível apagar a conta durante uma entrega")

    try:
        db.delete(entregador)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AcaoNaoPermitida(
            "Não foi possível remover: existem dados vinculados a este entregador"
        )
