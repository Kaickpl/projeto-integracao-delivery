from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.core.autorizacao import exigir_escopo_leitura_perfis
from src.core.database import get_db
from src.modules.perfil_usuario.perfil import Perfil
from src.modules.perfil_usuario.schemas import PerfilLeituraResponse

router = APIRouter(prefix="/v1/perfis", tags=["perfis para serviços"])


@router.get(
    "/{perfil_id}",
    response_model=PerfilLeituraResponse,
    summary="Consultar dados mínimos do perfil",
    description="Exige token M2M com audiência de Perfis e escopo perfis:ler.",
    responses={401: {"description": "Token inválido ou expirado"}, 403: {"description": "Escopo insuficiente"}, 503: {"description": "JWKS indisponível"}},
)
def obter_perfil(
    perfil_id: UUID,
    _claims: dict = Depends(exigir_escopo_leitura_perfis),
    db: Session = Depends(get_db),
):
    perfil = db.get(Perfil, perfil_id)
    if perfil is None:
        raise HTTPException(404, "Perfil não encontrado")
    return perfil
