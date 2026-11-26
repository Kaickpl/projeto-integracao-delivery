"""Teste ponta a ponta contra Auth, Perfis e RBAC locais e isolados."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
import re
import secrets
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from urllib.parse import quote_plus


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


def _validar_no_rbac(client: httpx.Client, rbac_url: str, token: str) -> httpx.Response:
    return client.post(
        f"{rbac_url}/v1/tokens/validar",
        headers={"Authorization": f"Bearer {token}"},
    )


def _reiniciar_replica_auth_e_aguardar(url: str) -> None:
    raiz = Path(__file__).resolve().parents[2]
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(raiz / "Docker-compose.integracao.yml"),
            "restart",
            "autenticacao_replica",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    limite = time.monotonic() + 30
    while time.monotonic() < limite:
        try:
            if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise AssertionError("A réplica do Auth não voltou após o reinício")


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
            headers={"Idempotency-Key": str(uuid.uuid4())},
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

        # A rota de admin exige token com perfis:alterar_status. O ADMIN é
        # criado antes pelo serviço preparar_admin_inicial da pilha local.
        sem_token = client.patch(
            f"{perfis_url}/admin/perfis/{conta_id}/status",
            json={"status": "ATIVO"},
        )
        assert sem_token.status_code == 401
        tokens_admin = _autenticar(
            client,
            auth_url,
            os.getenv("INTEGRATION_ADMIN_EMAIL", "admin-integracao@example.com"),
            os.getenv("INTEGRATION_ADMIN_SENHA", "Admin-integracao-2026"),
        )
        ativacao = client.patch(
            f"{perfis_url}/admin/perfis/{conta_id}/status",
            json={"status": "ATIVO"},
            headers={"Authorization": f"Bearer {tokens_admin['access_token']}"},
        )
        assert ativacao.status_code == 200, ativacao.text

        # Worker de Notificações: escopo mínimo, audiência de Perfis e validação
        # local por JWKS na própria rota protegida, sem chamada ao endpoint RBAC.
        credencial_m2m = base64.b64encode(
            b"worker-notificacoes-financeiro:segredo-perfis-apenas-teste-local"
        ).decode()
        token_m2m = client.post(
            f"{auth_url}/v1/oauth/tokens",
            data={
                "grant_type": "client_credentials",
                "resource": "http://perfis:8002",
                "scope": "perfis:ler",
            },
            headers={"Authorization": f"Basic {credencial_m2m}"},
        )
        assert token_m2m.status_code == 200, token_m2m.text
        assert "refresh_token" not in token_m2m.json()
        perfil_lido = client.get(
            f"{perfis_url}/v1/perfis/{conta_id}",
            headers={"Authorization": f"Bearer {token_m2m.json()['access_token']}"},
        )
        assert perfil_lido.status_code == 200, perfil_lido.text
        assert perfil_lido.json() == {
            "id": conta_id,
            "nome": "Cliente de integração",
            "email": email,
        }

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
        validacao_rbac = _validar_no_rbac(client, rbac_url, primeiro["access_token"])
        assert validacao_rbac.status_code == 200, validacao_rbac.text
        assert validacao_rbac.json()["role"] == "CLIENTE"

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

        validacao_revogado = _validar_no_rbac(
            client, rbac_url, segunda_sessao["access_token"]
        )
        assert validacao_revogado.status_code == 401
        assert validacao_revogado.json() == {
            "erro": True,
            "mensagem": "Token inválido, expirado ou revogado",
        }

        terceira_sessao = _autenticar(client, auth_url, email, senha)
        logout_por_access_token = client.post(
            f"{bases['AUTH_REPLICA']}/v1/oauth/revogar",
            data={
                "token": terceira_sessao["access_token"],
                "token_type_hint": "access_token",
            },
        )
        assert logout_por_access_token.status_code == 200
        logout_repetido = client.post(
            f"{bases['AUTH']}/v1/oauth/revogar",
            data={"token": terceira_sessao["refresh_token"]},
        )
        assert logout_repetido.status_code == 200
        renovacao_apos_logout = client.post(
            f"{auth_url}/v1/oauth/tokens",
            data={
                "grant_type": "refresh_token",
                "refresh_token": terceira_sessao["refresh_token"],
            },
        )
        assert renovacao_apos_logout.status_code == 401
        assert _validar_no_rbac(
            client, rbac_url, terceira_sessao["access_token"]
        ).status_code == 401

        sessao_concorrente = _autenticar(client, auth_url, email, senha)
        with ThreadPoolExecutor(max_workers=2) as executor:
            renovacao_futura = executor.submit(
                httpx.post,
                f"{auth_url}/v1/oauth/tokens",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": sessao_concorrente["refresh_token"],
                },
                timeout=10,
            )
            logout_futuro = executor.submit(
                httpx.post,
                f"{bases['AUTH_REPLICA']}/v1/oauth/revogar",
                data={"token": sessao_concorrente["refresh_token"]},
                timeout=10,
            )
            renovacao_concorrente = renovacao_futura.result()
            logout_concorrente = logout_futuro.result()
        assert logout_concorrente.status_code == 200
        assert renovacao_concorrente.status_code in {200, 401}
        assert _validar_no_rbac(
            client, rbac_url, sessao_concorrente["access_token"]
        ).status_code == 401
        if renovacao_concorrente.status_code == 200:
            assert _validar_no_rbac(
                client, rbac_url, renovacao_concorrente.json()["access_token"]
            ).status_code == 401

        if os.getenv("INTEGRATION_RESTART_AUTH_REPLICA") == "1":
            _reiniciar_replica_auth_e_aguardar(bases["AUTH_REPLICA"])
            refresh_apos_reinicio = client.post(
                f"{bases['AUTH_REPLICA']}/v1/oauth/tokens",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": terceira_sessao["refresh_token"],
                },
            )
            assert refresh_apos_reinicio.status_code == 401
            assert _validar_no_rbac(
                client, rbac_url, terceira_sessao["access_token"]
            ).status_code == 401


def test_client_credentials_emite_token_limitado_validado_por_jwks_e_rbac():
    bases = _ambiente_integracao()
    auth_url, rbac_url = bases["AUTH"], bases["RBAC"]
    client_id = os.getenv("INTEGRATION_M2M_CLIENT_ID", "teste-worker-financeiro")
    secret = os.getenv("INTEGRATION_M2M_CLIENT_SECRET", "segredo-m2m-apenas-teste-local")
    audience = os.getenv("INTEGRATION_M2M_AUDIENCE", "https://financeiro.example.test")
    escopo = "pagamentos:ler"
    with httpx.Client(timeout=10) as client:
        metadados = client.get(f"{auth_url}/.well-known/oauth-authorization-server")
        assert metadados.status_code == 200
        assert "client_credentials" in metadados.json()["grant_types_supported"]

        basic = base64.b64encode(
            f"{quote_plus(client_id)}:{quote_plus(secret)}".encode()
        ).decode()
        emissao = client.post(
            f"{auth_url}/v1/oauth/tokens",
            headers={"Authorization": f"Basic {basic}"},
            data={
                "grant_type": "client_credentials",
                "resource": audience,
                "scope": escopo,
            },
        )
        assert emissao.status_code == 200, emissao.text
        tokens = emissao.json()
        assert tokens["token_type"] == "Bearer"
        assert tokens["expires_in"] == 600
        assert "refresh_token" not in tokens

        jwks = client.get(f"{auth_url}/.well-known/jwks.json").json()
        header = jwt.get_unverified_header(tokens["access_token"])
        chave = next(chave for chave in jwks["keys"] if chave["kid"] == header["kid"])
        claims = jwt.decode(
            tokens["access_token"],
            jwt.PyJWK.from_dict(chave).key,
            algorithms=["RS256"],
            issuer=os.getenv("INTEGRATION_AUTH_ISSUER", "http://127.0.0.1:18001"),
            audience=audience,
        )
        assert claims["sub"] == f"servico:{client_id}"
        assert claims["client_id"] == client_id
        assert claims["scope"] == escopo
        assert "role" not in claims and "sid" not in claims

        emissao_replica = client.post(
            f"{bases['AUTH_REPLICA']}/v1/oauth/tokens",
            headers={"Authorization": f"Basic {basic}"},
            data={
                "grant_type": "client_credentials",
                "resource": audience,
                "scope": escopo,
            },
        )
        assert emissao_replica.status_code == 200, emissao_replica.text
        assert "refresh_token" not in emissao_replica.json()

        def solicitar_em(url):
            return httpx.post(
                f"{url}/v1/oauth/tokens",
                headers={"Authorization": f"Basic {basic}"},
                data={
                    "grant_type": "client_credentials",
                    "resource": audience,
                    "scope": escopo,
                },
                timeout=10,
            )

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(
                    solicitar_em,
                    bases["AUTH"] if indice % 2 else bases["AUTH_REPLICA"],
                )
                for indice in range(4)
            ]
            concorrentes = [futuro.result() for futuro in futures]
        assert all(resposta.status_code == 200 for resposta in concorrentes)

        if os.getenv("INTEGRATION_RESTART_AUTH_REPLICA") == "1":
            _reiniciar_replica_auth_e_aguardar(bases["AUTH_REPLICA"])
            apos_reinicio = solicitar_em(bases["AUTH_REPLICA"])
            assert apos_reinicio.status_code == 200, apos_reinicio.text
            assert "refresh_token" not in apos_reinicio.json()

        autorizado = client.post(
            f"{rbac_url}/v1/tokens/servico/validar",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            json={"audiencia": audience, "escopos": [escopo]},
        )
        assert autorizado.status_code == 200, autorizado.text

        negado = client.post(
            f"{rbac_url}/v1/tokens/servico/validar",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            json={"audiencia": audience, "escopos": ["pagamentos:estornar"]},
        )
        assert negado.status_code == 403
