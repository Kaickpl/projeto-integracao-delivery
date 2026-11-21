from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.modules.entregador import service
from src.modules.entregador.schemas import (
    EntregadorCreate,
    EntregadorResponse,
    EntregadorUpdate,
    StatusEntregadorUpdate,
)
from src.modules.perfil_usuario.entregador import StatusEntregador

router = APIRouter(prefix="/entregadores", tags=["entregadores"])


@router.post("", response_model=EntregadorResponse, status_code=201)
def cadastrar_entregador(dados: EntregadorCreate, db: Session = Depends(get_db)):
    return service.cadastrar_entregador(db, dados)


@router.get("", response_model=list[EntregadorResponse])
def listar_entregadores(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return service.listar_entregadores(db, skip=skip, limit=limit)


@router.get("/status/{status_entregador}", response_model=list[EntregadorResponse])
def listar_entregadores_por_status(
    status_entregador: StatusEntregador,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return service.listar_entregadores(db, status_entregador, skip, limit)


@router.get("/{entregador_id}", response_model=EntregadorResponse)
def buscar_entregador(entregador_id: UUID, db: Session = Depends(get_db)):
    return service.buscar_entregador(db, entregador_id)


@router.patch("/{entregador_id}", response_model=EntregadorResponse)
def editar_perfil(
    entregador_id: UUID, dados: EntregadorUpdate, db: Session = Depends(get_db)
):
    return service.atualizar_entregador(db, entregador_id, dados)


@router.patch("/{entregador_id}/status", response_model=EntregadorResponse)
def alterar_status_entregador(
    entregador_id: UUID, dados: StatusEntregadorUpdate, db: Session = Depends(get_db)
):
    return service.alterar_status_entregador(db, entregador_id, dados.status_entregador)


@router.delete("/{entregador_id}", status_code=204)
def apagar_conta(entregador_id: UUID, db: Session = Depends(get_db)):
    service.remover_entregador(db, entregador_id)
