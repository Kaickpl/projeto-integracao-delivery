import httpx

from src.core.config import settings
from src.core.exceptions import AcaoNaoPermitida, ServicoIndisponivel


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
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            raise AcaoNaoPermitida(
                "A credencial já existe com dados diferentes; reutilize a chave e os dados originais"
            ) from None
        raise ServicoIndisponivel(
            "Não foi possível provisionar a identidade no Auth/RBAC"
        ) from None
    except httpx.HTTPError:
        raise ServicoIndisponivel("Não foi possível provisionar a identidade no Auth/RBAC") from None


def remover_papel(conta_id) -> None:
    """Remove o papel da conta no RBAC. Idempotente: 204 mesmo sem papel."""
    try:
        resposta = httpx.delete(
            f"{settings.AUTORIZACAO_URL.rstrip('/')}/v1/interno/contas/{conta_id}/papel",
            headers={"Authorization": f"Bearer {settings.AUTORIZACAO_SERVICE_TOKEN}"},
            timeout=settings.AUTORIZACAO_TIMEOUT,
        )
        resposta.raise_for_status()
    except httpx.HTTPError:
        raise ServicoIndisponivel(
            "Não foi possível remover o papel da conta no RBAC"
        ) from None
