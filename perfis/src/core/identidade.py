import httpx

from src.core.config import settings
from src.core.exceptions import ServicoIndisponivel


def criar_credencial_e_associar_papel(conta_id, email: str, senha: str, role: str) -> None:
    timeout = settings.VIACEP_TIMEOUT
    try:
        credencial = httpx.post(
            f"{settings.AUTENTICACAO_URL.rstrip('/')}/v1/interno/credenciais",
            headers={"Authorization": f"Bearer {settings.AUTENTICACAO_SERVICE_TOKEN}"},
            json={"conta_id": str(conta_id), "email": email, "senha": senha, "tipo_conta": role},
            timeout=timeout,
        )
        credencial.raise_for_status()
        papel = httpx.put(
            f"{settings.AUTORIZACAO_URL.rstrip('/')}/v1/interno/contas/{conta_id}/papel",
            headers={"Authorization": f"Bearer {settings.AUTORIZACAO_SERVICE_TOKEN}"},
            json={"role": role},
            timeout=timeout,
        )
        papel.raise_for_status()
    except httpx.HTTPError:
        raise ServicoIndisponivel("Não foi possível provisionar a identidade no Auth/RBAC") from None
