from fastapi import APIRouter

from src.modules.endereco import service
from src.modules.endereco.schemas import CepResponse

router = APIRouter(prefix="/enderecos", tags=["enderecos"])


@router.get(
    "/cep/{cep}",
    response_model=CepResponse,
    responses={
        404: {"description": "CEP não encontrado"},
        422: {"description": "CEP sem 8 dígitos"},
        503: {"description": "Serviço de CEP fora do ar"},
    },
)
def buscar_cep(cep: str):

    return service.consultar_cep(cep)
