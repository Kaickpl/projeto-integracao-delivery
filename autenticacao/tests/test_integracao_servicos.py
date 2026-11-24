"""Teste ponta a ponta contra Auth, Perfis e RBAC locais e isolados."""
import base64
import hashlib
import os
import re
import secrets
import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest


def _ambiente_integracao():
    if os.getenv("RUN_CROSS_SERVICE_INTEGRATION") != "1":
        pytest.skip("Defina RUN_CROSS_SERVICE_INTEGRATION=1 para usar a pilha local isolada")
    nome_banco = os.getenv("INTEGRATION_DATABASE_NAME", "")
    if not re.fullmatch(r"delivery_teste[A-Za-z0-9_]*", nome_banco):
        pytest.fail("INTEGRATION_DATABASE_NAME deve começar com delivery_teste")
    bases = {
        nome: os.getenv(variavel, "")
        for nome, variavel in (
            ("AUTH", "INTEGRATION_AUTH_URL"),
            ("AUTH_REPLICA", "INTEGRATION_AUTH_REPLICA_URL"),
            ("PERFIS", "INTEGRATION_PERFIS_URL"),
            ("RBAC", "INTEGRATION_RBAC_URL"),
        )
    }
    for nome, base in bases.items():
        parsed = urlsplit(base)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
            pytest.fail(f"INTEGRATION_{nome}_URL deve apontar para localhost")
    for nome in ("INTEGRATION_PERFIS_TOKEN", "INTEGRATION_RBAC_TOKEN"):
        if not os.getenv(nome):
            pytest.fail(f"Configure {nome} com o token de teste da pilha local")
    return bases


def _cpf_valido() -> str:
    numeros = [secrets.randbelow(10) for _ in range(9)]
    if len(set(numeros)) == 1:
        numeros[0] = (numeros[0] + 1) % 10
    for peso_inicial in (10, 11):
        soma = sum(numero * peso for numero, peso in zip(numeros, range(peso_inicial, 1, -1)))
        digito = 0 if soma % 11 < 2 else 11 - soma % 11
        numeros.append(digito)
    return "".join(map(str, numeros))


def _desafio(verificador: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()


def _autenticar(client: httpx.Client, auth_url: str, email: str, senha: str) -> dict:
    verificador = secrets.token_urlsafe(32)
    desafio = _desafio(verificador)
    state = secrets.token_urlsafe(24)
    parametros = {
        "client_id": "delivery-app",
        "redirect_uri": "http://localhost:3000/oauth/callback",
        "response_type": "code",
        "code_challenge": desafio,
        "code_challenge_method": "S256",
        "state": state,
    }
    pagina = client.get(f"{auth_url}/v1/oauth/autorizar", params=parametros)
    assert pagina.status_code == 200
    resposta_login = client.post(
        f"{auth_url}/v1/oauth/entrar",
        data={**parametros, "email": email, "senha": senha},
    )
    assert resposta_login.status_code == 303
    destino = urlsplit(resposta_login.headers["location"])
    retornados = parse_qs(destino.query)
    assert retornados["state"] == [state]
    tokens = client.post(
        f"{auth_url}/v1/oauth/tokens",
        data={
            "grant_type": "authorization_code",
            "code": retornados["code"][0],
            "code_verifier": verificador,
            "client_id": parametros["client_id"],
            "redirect_uri": parametros["redirect_uri"],
        },
    )
    assert tokens.status_code == 200, tokens.text
    return tokens.json()


def _introspeccionar(client: httpx.Client, auth_url: str, token: str, cabecalho: dict) -> dict:
    resposta = client.post(
        f"{auth_url}/v1/oauth/introspeccao",
        json={"token": token},
        headers=cabecalho,
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def test_cadastro_login_refresh_revogacao_status_e_papel_nos_tres_servicos():
    bases = _ambiente_integracao()
    auth_url, perfis_url, rbac_url = bases["AUTH"], bases["PERFIS"], bases["RBAC"]
    token_perfis = os.environ["INTEGRATION_PERFIS_TOKEN"]
    token_rbac = os.environ["INTEGRATION_RBAC_TOKEN"]
    senha = "Senha-integracao-2026!"
    email = f"teste-{uuid.uuid4().hex}@example.com"

    with httpx.Client(timeout=10, follow_redirects=False) as client:
        for nome, base in bases.items():
            rota_saude = "/health/db" if nome == "PERFIS" else "/health"
            resposta = client.get(f"{base}{rota_saude}")
            assert resposta.status_code == 200, f"{nome}: {resposta.text}"

        cadastro = client.post(
            f"{perfis_url}/clientes",
            json={
                "nome": "Cliente de integração",
                "cpf": _cpf_valido(),
                "email": email,
                "senha": senha,
                "telefone": "71999990000",
            },
        )
        assert cadastro.status_code == 201, cadastro.text
        conta_id = cadastro.json()["id"]
        assert cadastro.json()["status"] == "PENDENTE_APROVACAO"

        status_headers = {"Authorization": f"Bearer {token_perfis}"}
        status_url = f"{perfis_url}/v1/interno/contas/{conta_id}/status"
        status = client.get(status_url, headers=status_headers)
        assert status.status_code == 200, status.text
        assert status.json()["status"] == "PENDENTE_APROVACAO"

        verificador_pendente = secrets.token_urlsafe(32)
        parametros_pendentes = {
            "client_id": "delivery-app",
            "redirect_uri": "http://localhost:3000/oauth/callback",
            "response_type": "code",
            "code_challenge": _desafio(verificador_pendente),
            "code_challenge_method": "S256",
            "state": secrets.token_urlsafe(20),
        }
        bloqueado = client.post(
            f"{auth_url}/v1/oauth/entrar",
            data={**parametros_pendentes, "email": email, "senha": senha},
        )
        assert bloqueado.status_code == 403
        assert "access_token" not in bloqueado.text

        ativacao = client.patch(
            f"{perfis_url}/admin/perfis/{conta_id}/status",
            json={"status": "ATIVO"},
        )
        assert ativacao.status_code == 200, ativacao.text

        papel_headers = {"Authorization": f"Bearer {token_rbac}"}
        papel = client.get(
            f"{rbac_url}/v1/interno/contas/{conta_id}/papel",
            headers=papel_headers,
        )
        assert papel.status_code == 200, papel.text
        assert papel.json()["role"] == "CLIENTE"

        primeiro = _autenticar(client, auth_url, email, senha)
        jwks = client.get(f"{auth_url}/.well-known/jwks.json").json()
        cabecalho_jwt = jwt.get_unverified_header(primeiro["access_token"])
        chave = next(item for item in jwks["keys"] if item["kid"] == cabecalho_jwt["kid"])
        claims = jwt.decode(
            primeiro["access_token"],
            jwt.PyJWK.from_dict(chave).key,
            algorithms=["RS256"],
            issuer="http://127.0.0.1:18001",
            audience="delivery-api",
        )
        assert cabecalho_jwt["typ"] == "at+jwt"
        assert claims["sub"] == conta_id
        assert claims["role"] == "CLIENTE"
        assert claims["exp"] - claims["iat"] == 25 * 60
        introspeccao_headers = {"Authorization": f"Bearer {token_rbac}"}
        assert _introspeccionar(client, auth_url, primeiro["access_token"], introspeccao_headers)["active"]

        refresh1 = primeiro["refresh_token"]
        renovado = client.post(
            f"{bases['AUTH_REPLICA']}/v1/oauth/tokens",
            data={"grant_type": "refresh_token", "refresh_token": refresh1},
        )
        assert renovado.status_code == 200, renovado.text
        refresh2 = renovado.json()["refresh_token"]
        assert refresh2 != refresh1

        reutilizado = client.post(
            f"{auth_url}/v1/oauth/tokens",
            data={"grant_type": "refresh_token", "refresh_token": refresh1},
        )
        assert reutilizado.status_code == 401
        assert not _introspeccionar(
            client, auth_url, renovado.json()["access_token"], introspeccao_headers
        )["active"]

        segunda_sessao = _autenticar(client, auth_url, email, senha)
        revogado = client.post(
            f"{bases['AUTH_REPLICA']}/v1/oauth/revogar",
            data={"token": segunda_sessao["refresh_token"]},
        )
        assert revogado.status_code == 200
        assert revogado.json() == {}
        assert not _introspeccionar(
            client, auth_url, segunda_sessao["access_token"], introspeccao_headers
        )["active"]
