from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.database import salvar_alteracoes
from src.core.exceptions import AcaoNaoPermitida, PerfilNaoEncontrado
from src.core.identidade import criar_credencial_e_associar_papel
from src.modules.admin.schemas import AdminCreate, PerfilAdminUpdate
from src.modules.perfil_usuario.admin import Admin
from src.modules.perfil_usuario.entregador import Entregador, StatusEntregador
from src.modules.perfil_usuario.loja import Loja, StatusFuncionamento
from src.modules.perfil_usuario.perfil import Perfil, StatusConta, TipoPerfil


def buscar_perfil(db: Session, perfil_id: UUID) -> Perfil:
    perfil = db.get(Perfil, perfil_id)
    if perfil is None:
        raise PerfilNaoEncontrado()
    return perfil


def listar_perfis(
    db: Session,
    tipo: TipoPerfil | None = None,
    status: StatusConta | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Perfil]:
    stmt = select(Perfil).order_by(Perfil.criado_em).offset(skip).limit(limit)
    if tipo:
        stmt = stmt.where(Perfil.tipo == tipo)
    if status:
        stmt = stmt.where(Perfil.status == status)
    return list(db.scalars(stmt))


def criar_admin(db: Session, dados: AdminCreate) -> Perfil:
    admin = Admin(**dados.model_dump(exclude={"senha"}), status=StatusConta.ATIVO)
    db.add(admin)
    db.flush()
    criar_credencial_e_associar_papel(admin.id, admin.email, dados.senha, "ADMIN")
    salvar_alteracoes(db)
    db.refresh(admin)
    return admin


def atualizar_perfil(db: Session, perfil_id: UUID, dados: PerfilAdminUpdate) -> Perfil:
    perfil = buscar_perfil(db, perfil_id)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(perfil, campo, valor)
    salvar_alteracoes(db)
    db.refresh(perfil)
    return perfil


def alterar_status(db: Session, perfil_id: UUID, novo_status: StatusConta) -> Perfil:
    perfil = buscar_perfil(db, perfil_id)
    perfil.status = novo_status
    # Conta que deixa de estar ativa (suspensa ou de volta à análise) sai de
    # operação: a loja fecha e o entregador fica inativo, mesmo no meio de
    # uma entrega. Ao reativar, cada um volta a abrir / ficar disponível
    # por conta própria.
    if novo_status != StatusConta.ATIVO:
        if isinstance(perfil, Loja):
            perfil.status_funcionamento = StatusFuncionamento.FECHADO
        elif isinstance(perfil, Entregador):
            perfil.status_entregador = StatusEntregador.INATIVO
    salvar_alteracoes(db)
    db.refresh(perfil)
    return perfil


def remover_perfil(db: Session, perfil_id: UUID) -> None:
    perfil = buscar_perfil(db, perfil_id)

    if perfil.tipo == TipoPerfil.ADMIN:
        total = db.scalar(
            select(func.count()).select_from(Perfil).where(Perfil.tipo == TipoPerfil.ADMIN)
        )
        if total <= 1:
            raise AcaoNaoPermitida("Não é possível remover o último admin")

    try:
        db.delete(perfil)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AcaoNaoPermitida(
            "Não foi possível remover: existem dados vinculados a este perfil"
        )
