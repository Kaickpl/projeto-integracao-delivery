import httpx

from src.core.config import settings
from src.core.exceptions import CepNaoEncontrado, DadosInvalidos, ServicoIndisponivel
from src.core.validators import cep_valido, limpar_cep

MENSAGEM_CEP_INDISPONIVEL = (

)


def consultar_cep(cep: str) -> dict:
    cep = limpar_cep(cep)
    if not cep_valido(cep):
        raise DadosInvalidos("CEP deve ter 8 dígitos")

    try:
        with httpx.Client(timeout=settings.VIACEP_TIMEOUT) as cliente:
            resposta = cliente.get(f"{settings.VIACEP_URL}/{cep}/json/")
            resposta.raise_for_status()
            dados = resposta.json()
    except (httpx.HTTPError, ValueError):
        # Fora do ar, lento demais ou respondeu algo que não é JSON.
        raise ServicoIndisponivel(MENSAGEM_CEP_INDISPONIVEL)

    if not isinstance(dados, dict):
        raise ServicoIndisponivel(MENSAGEM_CEP_INDISPONIVEL)
    if dados.get("erro"):
        raise CepNaoEncontrado()

    return {
        "cep": cep,
        "logradouro": dados.get("logradouro") or None,
        "bairro": dados.get("bairro") or None,
        "cidade": dados.get("localidade"),
        "uf": dados.get("uf"),
    }
