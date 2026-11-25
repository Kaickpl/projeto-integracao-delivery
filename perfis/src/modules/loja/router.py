from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.modules.loja import service
from src.modules.loja.schemas import (
    Horario,
    HorariosUpdate,
    LojaCreate,
    LojaInformacoesUpdate,
    LojaPerfilUpdate,
    LojaResponse,
    StatusFuncionamentoUpdate,
)
from src.modules.perfil_usuario.loja import CategoriaLoja, StatusFuncionamento

router = APIRouter(prefix="/lojas", tags=["lojas"])


@router.post("", response_model=LojaResponse, status_code=201)
def cadastrar_loja(
    dados: LojaCreate,
    chave_idempotencia: UUID = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    return service.cadastrar_loja(db, dados, chave_idempotencia)


@router.get("", response_model=list[LojaResponse])
def buscar_lojas(
    nome: str | None = Query(
        None, min_length=1, max_length=150, description="Parte do nome da loja"
    ),
    categoria: CategoriaLoja | None = None,
    status_funcionamento: StatusFuncionamento | None = None,
    cidade: str | None = Query(None, min_length=1, max_length=100),
    bairro: str | None = Query(None, min_length=1, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Busca de lojas para o cliente. Os filtros podem ser combinados.

    Só aparecem lojas com a conta ativa (aprovadas pelo admin). As abertas
    vêm primeiro.
    """
    return service.buscar_lojas(
        db, nome, categoria, status_funcionamento, cidade, bairro, skip, limit
    )


@router.get("/{loja_id}", response_model=LojaResponse)
def buscar_loja(loja_id: UUID, db: Session = Depends(get_db)):
    return service.buscar_loja(db, loja_id)


@router.patch("/{loja_id}", response_model=LojaResponse)
def editar_perfil(loja_id: UUID, dados: LojaPerfilUpdate, db: Session = Depends(get_db)):
    """Dados da conta: nome, e-mail, telefone e razão social."""
    return service.atualizar_perfil(db, loja_id, dados)


@router.patch("/{loja_id}/informacoes", response_model=LojaResponse)
def editar_informacoes(
    loja_id: UUID, dados: LojaInformacoesUpdate, db: Session = Depends(get_db)
):
    """O que o cliente vê: descrição, imagem, categoria, taxa, tempo e endereço."""
    return service.atualizar_informacoes(db, loja_id, dados)


@router.get("/{loja_id}/horarios", response_model=list[Horario])
def listar_horarios(loja_id: UUID, db: Session = Depends(get_db)):
    """Horários de funcionamento, por dia da semana."""
    return service.listar_horarios(db, loja_id)


@router.put("/{loja_id}/horarios", response_model=list[Horario])
def definir_horarios(
    loja_id: UUID, dados: HorariosUpdate, db: Session = Depends(get_db)
):

    return service.definir_horarios(db, loja_id, dados)


@router.patch("/{loja_id}/status", response_model=LojaResponse)
def alterar_status_funcionamento(
    loja_id: UUID, dados: StatusFuncionamentoUpdate, db: Session = Depends(get_db)
):
    return service.alterar_status_funcionamento(db, loja_id, dados.status_funcionamento)


@router.delete("/{loja_id}", status_code=204)
def apagar_loja(loja_id: UUID, db: Session = Depends(get_db)):
    service.remover_loja(db, loja_id)
