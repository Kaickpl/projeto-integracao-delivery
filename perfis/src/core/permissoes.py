"""Autorização das rotas de Perfis com as permissões do RBAC.

Cada rota protegida declara a permissão necessária. O token do usuário é
validado online no RBAC (`POST /v1/tokens/validar`), que confere a sessão no
Auth e devolve o papel e as permissões atuais desse papel. Não há cache: uma
permissão removida no RBAC vale já na próxima requisição.

Permissões `*_proprio` só liberam a ação quando o id da rota é a própria conta
(`perfil.id == conta_id`). A posse é conferida aqui, porque só Perfis sabe de
quem é cada perfil.
"""
from dataclasses import dataclass
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.config import settings
from src.core.erros import ErroResponse
from src.core.exceptions import ServicoIndisponivel

MENSAGEM_TOKEN_INVALIDO = "Token inválido, expirado ou revogado"
MENSAGEM_ACESSO_NEGADO = "Acesso não permitido"
MENSAGEM_RBAC_INDISPONIVEL = "Não foi possível verificar a autorização"

RESPOSTAS_PROTEGIDAS = {
    401: {"model": ErroResponse, "description": "Token ausente, inválido, expirado ou revogado"},
    403: {"model": ErroResponse, "description": "Sem a permissão necessária ou o recurso não é da conta"},
    503: {"model": ErroResponse, "description": "RBAC ou Auth indisponível"},
}

esquema_bearer = HTTPBearer(
    auto_error=False,
    description="Access token do usuário emitido pelo Auth",
)


@dataclass(frozen=True)
class UsuarioAutenticado:
    conta_id: UUID
    role: str
    permissoes: frozenset[str]


def _nao_autenticado() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=MENSAGEM_TOKEN_INVALIDO,
        headers={"WWW-Authenticate": "Bearer"},
    )


def usuario_autenticado(
    credenciais: HTTPAuthorizationCredentials | None = Depends(esquema_bearer),
) -> UsuarioAutenticado:
    token = credenciais.credentials.strip() if credenciais else ""
    if not token:
        raise _nao_autenticado()

    try:
        resposta = httpx.post(
            f"{settings.AUTORIZACAO_URL.rstrip('/')}/v1/tokens/validar",
            headers={"Authorization": f"Bearer {token}"},
            timeout=settings.AUTORIZACAO_TIMEOUT,
        )
    except httpx.HTTPError:
        raise ServicoIndisponivel(MENSAGEM_RBAC_INDISPONIVEL) from None
    if resposta.status_code == 401:
        raise _nao_autenticado()
    if resposta.status_code != 200:
        # Falha fechada: sem resposta confiável do RBAC, nada é liberado.
        raise ServicoIndisponivel(MENSAGEM_RBAC_INDISPONIVEL)

    try:
        dados = resposta.json()
        permissoes = dados["permissoes"]
        if not isinstance(permissoes, list) or any(
            not isinstance(item, str) for item in permissoes
        ):
            raise TypeError
        return UsuarioAutenticado(
            conta_id=UUID(dados["conta_id"]),
            role=str(dados["role"]),
            permissoes=frozenset(permissoes),
        )
    except (ValueError, KeyError, TypeError):
        raise ServicoIndisponivel(MENSAGEM_RBAC_INDISPONIVEL) from None


def _eh_dono(request: Request, parametro: str, usuario: UsuarioAutenticado) -> bool:
    try:
        return UUID(request.path_params[parametro]) == usuario.conta_id
    except (KeyError, ValueError):
        return False


def exigir_permissao(
    qualquer: str | None = None,
    proprio: str | None = None,
    dono: str | None = None,
):
    """Cria a dependência que libera a rota.

    - `qualquer`: permissão que libera a ação sobre qualquer recurso.
    - `proprio`: permissão que libera a ação só quando o parâmetro de rota
      `dono` é a conta do usuário.
    """
    if not qualquer and not proprio:
        raise ValueError("Informe ao menos uma permissão")
    if proprio and not dono:
        raise ValueError("Permissão do próprio recurso exige o parâmetro dono")

    def dependencia(
        request: Request,
        usuario: UsuarioAutenticado = Depends(usuario_autenticado),
    ) -> UsuarioAutenticado:
        if qualquer and qualquer in usuario.permissoes:
            return usuario
        if proprio and proprio in usuario.permissoes and _eh_dono(request, dono, usuario):
            return usuario
        raise HTTPException(status_code=403, detail=MENSAGEM_ACESSO_NEGADO)

    return dependencia


def protegida(
    qualquer: str | None = None,
    proprio: str | None = None,
    dono: str | None = None,
) -> dict:
    """Argumentos para o decorator da rota: dependência e respostas no OpenAPI.

    Ex.: @router.patch("/{loja_id}", **protegida(qualquer="perfis:editar_qualquer",
         proprio="perfil:editar_proprio", dono="loja_id"))
    """
    return {
        "dependencies": [Depends(exigir_permissao(qualquer, proprio, dono))],
        "responses": RESPOSTAS_PROTEGIDAS,
    }
