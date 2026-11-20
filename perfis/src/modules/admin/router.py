from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.modules.admin import service
from src.modules.admin.schemas import (
    AdminCreate,
    PerfilAdminResponse,
    PerfilAdminUpdate,
    StatusUpdate,
)
from src.modules.perfil_usuario.perfil import StatusConta, TipoPerfil

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/perfis", response_model=list[PerfilAdminResponse])
def listar_perfis(
    tipo: TipoPerfil | None = None,
    status: StatusConta | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return service.listar_perfis(db, tipo, status, skip, limit)


@router.get("/perfis/{perfil_id}", response_model=PerfilAdminResponse)
def buscar_perfil(perfil_id: UUID, db: Session = Depends(get_db)):
    return service.buscar_perfil(db, perfil_id)


@router.post("/admins", response_model=PerfilAdminResponse, status_code=201)
def criar_admin(dados: AdminCreate, db: Session = Depends(get_db)):
    return service.criar_admin(db, dados)


@router.patch("/perfis/{perfil_id}", response_model=PerfilAdminResponse)
def atualizar_perfil(perfil_id: UUID, dados: PerfilAdminUpdate, db: Session = Depends(get_db)):
    return service.atualizar_perfil(db, perfil_id, dados)


@router.patch("/perfis/{perfil_id}/status", response_model=PerfilAdminResponse)
def alterar_status_de_perfil(perfil_id: UUID, dados: StatusUpdate, db: Session = Depends(get_db)):
    return service.alterar_status(db, perfil_id, dados.status)


@router.delete("/perfis/{perfil_id}", status_code=204)
def remover_perfil(perfil_id: UUID, db: Session = Depends(get_db)):
    service.remover_perfil(db, perfil_id)