from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from src.core.database import salvar_alteracoes
from src.core.exceptions import (
    AcaoNaoPermitida,
    DadosInvalidos,
    PerfilNaoEncontrado,
)
from src.core.provisionamento import provisionar_cadastro, remover_cadastro
from src.modules.loja.schemas import (
    MENSAGEM_TEMPO_ESTIMADO,
    HorariosUpdate,
    LojaCreate,
    LojaInformacoesUpdate,
    LojaPerfilUpdate,
    tempo_estimado_invalido,
)
from src.modules.perfil_usuario.endereco import Endereco
from src.modules.perfil_usuario.horario_funcionamento import HorarioFuncionamento
from src.modules.perfil_usuario.loja import CategoriaLoja, Loja, StatusFuncionamento
from src.modules.perfil_usuario.perfil import StatusConta


def _salvar(db: Session, loja: Loja) -> Loja:
    loja.atualizado_em = func.now()
    salvar_alteracoes(db)
    db.refresh(loja)
    return loja


def cadastrar_loja(
    db: Session, dados: LojaCreate, chave_idempotencia: UUID
) -> Loja:
    loja = Loja(
        **dados.model_dump(exclude={"endereco", "senha"}),
        valor_minimo_pedido=0,
        endereco=Endereco(**dados.endereco.model_dump()),
        status=StatusConta.PENDENTE_APROVACAO,
        status_funcionamento=StatusFuncionamento.FECHADO,
    )
    return provisionar_cadastro(
        db,
        loja,
        senha=dados.senha,
        role="LOJA",
        chave_idempotencia=chave_idempotencia,
        dados_cadastro=dados.model_dump(exclude={"senha"}),
    )


def buscar_loja(db: Session, loja_id: UUID) -> Loja:
    loja = db.get(Loja, loja_id)
    if loja is None:
        raise PerfilNaoEncontrado("Loja não encontrada")
    return loja


def buscar_lojas(
    db: Session,
    nome: str | None = None,
    categoria: CategoriaLoja | None = None,
    status_funcionamento: StatusFuncionamento | None = None,
    cidade: str | None = None,
    bairro: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Loja]:

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
    if cidade or bairro:
        stmt = stmt.join(Loja.endereco)
        if cidade:
            stmt = stmt.where(Endereco.cidade.icontains(cidade, autoescape=True))
        if bairro:
            stmt = stmt.where(Endereco.bairro.icontains(bairro, autoescape=True))
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


def listar_horarios(db: Session, loja_id: UUID) -> list[HorarioFuncionamento]:
    return buscar_loja(db, loja_id).horarios


def definir_horarios(
    db: Session, loja_id: UUID, dados: HorariosUpdate
) -> list[HorarioFuncionamento]:
    loja = buscar_loja(db, loja_id)
    loja.horarios.clear()
    db.flush()
    loja.horarios.extend(
        HorarioFuncionamento(**horario.model_dump()) for horario in dados.horarios
    )
    _salvar(db, loja)
    return loja.horarios


def alterar_status_funcionamento(
    db: Session, loja_id: UUID, novo_status: StatusFuncionamento
) -> Loja:
    loja = buscar_loja(db, loja_id)
    if novo_status == StatusFuncionamento.ABERTO and loja.status != StatusConta.ATIVO:
        raise AcaoNaoPermitida("Só lojas com a conta ativa podem abrir")
    loja.status_funcionamento = novo_status
    return _salvar(db, loja)


def remover_loja(db: Session, loja_id: UUID) -> None:
    loja = buscar_loja(db, loja_id)
    if loja.status_funcionamento == StatusFuncionamento.ABERTO:
        raise AcaoNaoPermitida("Feche a loja antes de apagar a conta")

    remover_cadastro(
        db, loja, "Não foi possível remover: existem dados vinculados a esta loja"
    )
