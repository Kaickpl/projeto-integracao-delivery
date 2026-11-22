from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from src.core.exceptions import (
    AcaoNaoPermitida,
    DadoDuplicado,
    DadosInvalidos,
    PerfilNaoEncontrado,
)
from src.modules.loja.schemas import (
    MENSAGEM_TEMPO_ESTIMADO,
    LojaCreate,
    LojaInformacoesUpdate,
    LojaPerfilUpdate,
    tempo_estimado_invalido,
)
from src.modules.perfil_usuario.endereco import Endereco
from src.modules.perfil_usuario.loja import CategoriaLoja, Loja, StatusFuncionamento
from src.modules.perfil_usuario.perfil import StatusConta


def _salvar(db: Session, loja: Loja) -> Loja:
    # As colunas da loja ficam em `lojas`, mas `atualizado_em` fica em
    # `perfis`; sem isso ele não muda quando só a parte da loja é alterada.
    loja.atualizado_em = func.now()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DadoDuplicado("CNPJ ou e-mail já cadastrado")
    db.refresh(loja)
    return loja


def cadastrar_loja(db: Session, dados: LojaCreate) -> Loja:
    # A conta começa aguardando a aprovação do admin e a loja começa fechada.
    loja = Loja(
        **dados.model_dump(exclude={"endereco"}),
        endereco=Endereco(**dados.endereco.model_dump()),
        status=StatusConta.PENDENTE_APROVACAO,
        status_funcionamento=StatusFuncionamento.FECHADO,
    )
    db.add(loja)
    return _salvar(db, loja)


def buscar_loja(db: Session, loja_id: UUID) -> Loja:
    # Se o id for de outro tipo de perfil (cliente, entregador...), volta None.
    loja = db.get(Loja, loja_id)
    if loja is None:
        raise PerfilNaoEncontrado("Loja não encontrada")
    return loja


def buscar_lojas(
    db: Session,
    nome: str | None = None,
    categoria: CategoriaLoja | None = None,
    status_funcionamento: StatusFuncionamento | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Loja]:
    """Busca feita pelo cliente: só aparecem lojas com a conta ativa.

    As abertas vêm primeiro; depois, ordem alfabética.
    """
    stmt = (
        select(Loja)
        .options(selectinload(Loja.endereco))
        .where(Loja.status == StatusConta.ATIVO)
        .order_by(
            case((Loja.status_funcionamento == StatusFuncionamento.ABERTO, 0), else_=1),
            Loja.nome,
            Loja.id,
        )
        .offset(skip)
        .limit(limit)
    )
    if nome:
        # Sem diferenciar maiúsculas; % e _ digitados são tratados como texto.
        stmt = stmt.where(Loja.nome.icontains(nome, autoescape=True))
    if categoria:
        stmt = stmt.where(Loja.categoria == categoria)
    if status_funcionamento:
        stmt = stmt.where(Loja.status_funcionamento == status_funcionamento)
    return list(db.scalars(stmt))


def atualizar_perfil(db: Session, loja_id: UUID, dados: LojaPerfilUpdate) -> Loja:
    loja = buscar_loja(db, loja_id)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(loja, campo, valor)
    return _salvar(db, loja)


def atualizar_informacoes(
    db: Session, loja_id: UUID, dados: LojaInformacoesUpdate
) -> Loja:
    loja = buscar_loja(db, loja_id)
    alteracoes = dados.model_dump(exclude_unset=True)
    endereco = alteracoes.pop("endereco", {})

    # Confere o tempo estimado como ele vai ficar depois da alteração.
    if tempo_estimado_invalido(
        alteracoes.get("tempo_estimado_min", loja.tempo_estimado_min),
        alteracoes.get("tempo_estimado_max", loja.tempo_estimado_max),
    ):
        raise DadosInvalidos(MENSAGEM_TEMPO_ESTIMADO)

    for campo, valor in alteracoes.items():
        setattr(loja, campo, valor)
    for campo, valor in endereco.items():
        setattr(loja.endereco, campo, valor)
    return _salvar(db, loja)


def alterar_status_funcionamento(
    db: Session, loja_id: UUID, novo_status: StatusFuncionamento
) -> Loja:
    loja = buscar_loja(db, loja_id)
    # Conta pendente ou suspensa não pode receber pedidos.
    if novo_status == StatusFuncionamento.ABERTO and loja.status != StatusConta.ATIVO:
        raise AcaoNaoPermitida("Só lojas com a conta ativa podem abrir")
    loja.status_funcionamento = novo_status
    return _salvar(db, loja)


def remover_loja(db: Session, loja_id: UUID) -> None:
    loja = buscar_loja(db, loja_id)
    if loja.status_funcionamento == StatusFuncionamento.ABERTO:
        raise AcaoNaoPermitida("Feche a loja antes de apagar a conta")

    try:
        # O endereço da loja é apagado junto (cascade do relacionamento).
        db.delete(loja)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AcaoNaoPermitida(
            "Não foi possível remover: existem dados vinculados a esta loja"
        )
