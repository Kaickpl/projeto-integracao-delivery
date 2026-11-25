import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.database import get_db
from src.modules.perfil_usuario.perfil import Perfil

router = APIRouter(prefix="/v1/interno", tags=["integração interna"])


class StatusContaResponse(BaseModel):
    conta_id: UUID
    status: str
    identidade_pronta: bool


def exigir_credencial_servico(authorization: str | None = Header(default=None)) -> None:
    esperada = settings.INTERNAL_SERVICE_TOKEN
    fornecida = authorization.removeprefix("Bearer ") if authorization else ""
    if not esperada or not secrets.compare_digest(fornecida, esperada):
        raise HTTPException(status_code=401, detail="Credencial de serviço inválida")


@router.get("/contas/{conta_id}/status", response_model=StatusContaResponse)
def consultar_status_conta(
    conta_id: UUID,
    _autenticado: None = Depends(exigir_credencial_servico),
    db: Session = Depends(get_db),
):
    perfil = db.get(Perfil, conta_id)
    if perfil is None:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    return StatusContaResponse(
        conta_id=perfil.id,
        status=perfil.status.value,
        identidade_pronta=perfil.identidade_pronta,
    )
