import httpx

from src.core.config import settings
from src.core.exceptions import CepNaoEncontrado, DadosInvalidos, ServicoIndisponivel
from src.core.validators import cep_valido, limpar_cep

MENSAGEM_CEP_INDISPONIVEL = (
    "Não foi possível consultar o CEP agora. "
    "Tente de novo ou preencha o endereço manualmente."
)


def consultar_cep(cep: str) -> dict:
    """Busca no ViaCEP o logradouro, o bairro, a cidade e a UF de um CEP."""
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
    # Para CEP que não existe, o ViaCEP responde 200 com {"erro": true}.
    if dados.get("erro"):
        raise CepNaoEncontrado()

    return {
        "cep": cep,
        # Vem "" em cidades com CEP único: o usuário digita.
        "logradouro": dados.get("logradouro") or None,
        "bairro": dados.get("bairro") or None,
        "cidade": dados.get("localidade"),
        "uf": dados.get("uf"),
    }
