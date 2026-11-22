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
    """Busca o endereço de um CEP (ViaCEP) para preencher o formulário.

    Aceita o CEP com ou sem hífen. O front chama esta rota quando o usuário
    termina de digitar o CEP e preenche logradouro, bairro, cidade e UF.
    """
    return service.consultar_cep(cep)
