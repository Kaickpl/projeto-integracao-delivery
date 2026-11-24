import base64
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from src.core.database import get_db
import src.main as principal
from src.main import app
from src.modules.oauth import router as rotas_oauth


def _db_teste():
    yield object()


def cliente_teste(monkeypatch):
    app.dependency_overrides[get_db] = _db_teste
    monkeypatch.setattr(
        rotas_oauth,
        "Settings",
        lambda: SimpleNamespace(
            OAUTH_CLIENT_ID="delivery-app",
            OAUTH_REDIRECT_URI="http://localhost:3000/oauth/callback",
            JWT_ISSUER="http://localhost:8001",
            OAUTH_CLIENT_CREDENTIALS_ENABLED=False,
        ),
    )
    monkeypatch.setattr(
        principal,
        "Settings",
        lambda: SimpleNamespace(JWT_ISSUER="http://localhost:8001"),
    )
    return TestClient(app, follow_redirects=False)


@pytest.mark.parametrize(
    ("campos", "senha", "campo_invalido"),
    [
        ({"conta_id": "00000000-0000-4000-8000-000000000001"}, "curta", "senha"),
        ({}, "senha-ficticia-para-teste", "conta_id"),
    ],
)
def test_erro_de_cadastro_preserva_campo_sem_expor_senha(
    monkeypatch, caplog, campos, senha, campo_invalido
):
    dados = {"email": "teste@example.test", "tipo_conta": "CLIENTE", "senha": senha, **campos}
    cliente = cliente_teste(monkeypatch)
    try:
        resposta = cliente.post("/v1/interno/credenciais", json=dados)
        assert resposta.status_code == 422
        assert resposta.json()["detail"][0]["loc"] == ["body", campo_invalido]
        assert senha not in resposta.text
        assert senha not in caplog.text
    finally:
        app.dependency_overrides.clear()


def test_tela_de_login_inicia_authorization_code_com_pkce(monkeypatch):
    cliente = cliente_teste(monkeypatch)
    try:
        resposta = cliente.get(
            "/v1/oauth/autorizar",
            params={
                "client_id": "delivery-app",
                "redirect_uri": "http://localhost:3000/oauth/callback",
                "response_type": "code",
                "code_challenge": "a" * 43,
                "code_challenge_method": "S256",
                "state": "estado-csrf",
            },
        )
        assert resposta.status_code == 200
        assert '<form method="post" action="/v1/oauth/entrar">' in resposta.text
        assert 'name="senha" type="password"' in resposta.text
        assert "estado-csrf" in resposta.text
    finally:
        app.dependency_overrides.clear()


def test_tela_de_login_rejeita_cliente_ou_pkce_invalido(monkeypatch):
    cliente = cliente_teste(monkeypatch)
    try:
        resposta = cliente.get(
            "/v1/oauth/autorizar",
            params={
                "client_id": "outro-cliente",
                "redirect_uri": "http://localhost:3000/oauth/callback",
                "response_type": "code",
                "code_challenge": "a" * 43,
                "code_challenge_method": "S256",
                "state": "estado",
            },
        )
        assert resposta.status_code == 400
        assert "senha" not in resposta.text
    finally:
        app.dependency_overrides.clear()


def test_login_redireciona_apenas_codigo_e_state(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        rotas_oauth.service,
        "autorizar",
        lambda *args: (chamadas.append(args), "codigo-descartavel")[1],
    )
    cliente = cliente_teste(monkeypatch)
    try:
        resposta = cliente.post(
            "/v1/oauth/entrar",
            data={
                "email": "cliente@example.test",
                "senha": "senha-de-teste",
                "client_id": "delivery-app",
                "redirect_uri": "http://localhost:3000/oauth/callback",
                "response_type": "code",
                "code_challenge": "b" * 43,
                "code_challenge_method": "S256",
                "state": "nonce-da-aplicacao",
            },
        )
        destino = urlsplit(resposta.headers["location"])
        parametros = parse_qs(destino.query)
        assert resposta.status_code == 303
        assert parametros == {"code": ["codigo-descartavel"], "state": ["nonce-da-aplicacao"]}
        assert chamadas[0][1:4] == (
            "cliente@example.test",
            "senha-de-teste",
            "delivery-app",
        )
    finally:
        app.dependency_overrides.clear()


def test_endpoint_de_tokens_usa_formulario_oauth(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        rotas_oauth.service,
        "trocar_codigo",
        lambda *args: (chamadas.append(args), {"access_token": "jwt", "refresh_token": "refresh"})[1],
    )
    cliente = cliente_teste(monkeypatch)
    try:
        resposta = cliente.post(
            "/v1/oauth/tokens",
            data={
                "grant_type": "authorization_code",
                "code": "codigo",
                "code_verifier": "v" * 43,
                "client_id": "delivery-app",
                "redirect_uri": "http://localhost:3000/oauth/callback",
            },
        )
        assert resposta.status_code == 200
        assert resposta.json()["access_token"] == "jwt"
        assert chamadas[0][1:] == (
            "codigo",
            "v" * 43,
            "delivery-app",
            "http://localhost:3000/oauth/callback",
        )
    finally:
        app.dependency_overrides.clear()


def test_endpoint_de_tokens_rejeita_grant_desconhecido(monkeypatch):
    cliente = cliente_teste(monkeypatch)
    try:
        resposta = cliente.post("/v1/oauth/tokens", data={"grant_type": "senha"})
        assert resposta.status_code == 400
        assert resposta.json()["detail"] == "grant_type inválido"
    finally:
        app.dependency_overrides.clear()


def test_client_credentials_exige_ativacao_e_autenticacao_basic(monkeypatch):
    cliente = cliente_teste(monkeypatch)
    try:
        desabilitado = cliente.post(
            "/v1/oauth/tokens",
            data={
                "grant_type": "client_credentials",
                "resource": "https://financeiro.test",
                "scope": "pagamentos:ler",
            },
        )
        assert desabilitado.status_code == 400
        assert desabilitado.json() == {
            "erro": True,
            "mensagem": "Grant não habilitado",
            "error": "unsupported_grant_type",
        }

        monkeypatch.setattr(
            rotas_oauth,
            "Settings",
            lambda: SimpleNamespace(OAUTH_CLIENT_CREDENTIALS_ENABLED=True),
        )
        sem_basic = cliente.post(
            "/v1/oauth/tokens",
            data={
                "grant_type": "client_credentials",
                "resource": "https://financeiro.test",
                "scope": "pagamentos:ler",
            },
        )
        assert sem_basic.status_code == 401
        assert sem_basic.json() == {
            "erro": True,
            "mensagem": "Cliente ou segredo inválido",
            "error": "invalid_client",
        }
    finally:
        app.dependency_overrides.clear()


def test_client_credentials_responde_token_sem_refresh(monkeypatch):
    cliente = cliente_teste(monkeypatch)
    authorization = "Basic " + base64.b64encode(b"financeiro-worker:segredo").decode()
    chamadas = []
    monkeypatch.setattr(
        rotas_oauth,
        "Settings",
        lambda: SimpleNamespace(OAUTH_CLIENT_CREDENTIALS_ENABLED=True),
    )
    monkeypatch.setattr(
        rotas_oauth.service,
        "emitir_token_cliente_servico",
        lambda *args: (chamadas.append(args), {"access_token": "jwt", "token_type": "Bearer"})[1],
    )
    try:
        resposta = cliente.post(
            "/v1/oauth/tokens",
            headers={"Authorization": authorization},
            data={
                "grant_type": "client_credentials",
                "resource": "https://financeiro.test",
                "scope": "pagamentos:ler notificacoes:enviar",
            },
        )
        assert resposta.status_code == 200
        assert resposta.json() == {"access_token": "jwt", "token_type": "Bearer"}
        assert chamadas[0][1:] == (
            "financeiro-worker",
            "segredo",
            "https://financeiro.test",
            ["pagamentos:ler", "notificacoes:enviar"],
        )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "dados,erro_esperado",
    [
        ({"scope": "pagamentos:ler"}, "invalid_request"),
        ({"resource": "financeiro", "scope": "pagamentos:ler"}, "invalid_target"),
        (
            {"resource": "https://financeiro.test", "scope": "pagamentos:ler pagamentos:ler"},
            "invalid_scope",
        ),
        ({"resource": "https://financeiro.test", "scope": 'pagamentos:"ler"'}, "invalid_scope"),
    ],
)
def test_client_credentials_rejeita_parametros_invalidos(monkeypatch, dados, erro_esperado):
    cliente = cliente_teste(monkeypatch)
    monkeypatch.setattr(
        rotas_oauth,
        "Settings",
        lambda: SimpleNamespace(OAUTH_CLIENT_CREDENTIALS_ENABLED=True),
    )
    authorization = "Basic " + base64.b64encode(b"worker:segredo").decode()
    try:
        resposta = cliente.post(
            "/v1/oauth/tokens",
            headers={"Authorization": authorization},
            data={"grant_type": "client_credentials", **dados},
        )
        assert resposta.status_code == 400
        assert resposta.json()["error"] == erro_esperado
        assert "access_token" not in resposta.json()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "falha,status,codigo",
    [
        (rotas_oauth.service.EscopoClienteNaoAutorizado(), 400, "invalid_scope"),
        (HTTPException(401, "Cliente ou segredo inválido"), 401, "invalid_client"),
        (HTTPException(503, "RBAC indisponível"), 503, "server_error"),
        (SQLAlchemyError("banco indisponível"), 503, "server_error"),
    ],
)
def test_client_credentials_mapeia_erros_sem_emitir_token(monkeypatch, falha, status, codigo):
    cliente = cliente_teste(monkeypatch)
    monkeypatch.setattr(
        rotas_oauth,
        "Settings",
        lambda: SimpleNamespace(OAUTH_CLIENT_CREDENTIALS_ENABLED=True),
    )

    def falhar(*_args):
        raise falha

    monkeypatch.setattr(rotas_oauth.service, "emitir_token_cliente_servico", falhar)
    authorization = "Basic " + base64.b64encode(b"worker:segredo").decode()
    try:
        resposta = cliente.post(
            "/v1/oauth/tokens",
            headers={"Authorization": authorization},
            data={
                "grant_type": "client_credentials",
                "resource": "https://financeiro.test",
                "scope": "pagamentos:ler",
            },
        )
        assert resposta.status_code == status
        assert resposta.json()["error"] == codigo
        assert resposta.json()["erro"] is True
        assert "access_token" not in resposta.json()
    finally:
        app.dependency_overrides.clear()


def test_basic_decodifica_credenciais_codificadas_e_rejeita_bytes_invalidos():
    valido = "Basic " + base64.b64encode(b"worker%2Bone:segredo%3Aextra").decode()
    invalido = "Basic " + base64.b64encode(bytes([255]) + b":segredo").decode()

    assert rotas_oauth._extrair_client_secret_basic(valido) == ("worker+one", "segredo:extra")
    assert rotas_oauth._extrair_client_secret_basic(invalido) is None


def test_validacao_direta_de_cliente_e_pkce_rejeita_parametros_inseguros(monkeypatch):
    cliente_teste(monkeypatch)
    try:
        with pytest.raises(HTTPException, match="response_type=code"):
            rotas_oauth._validar_cliente(
                "delivery-app",
                "http://localhost:3000/oauth/callback",
                "token",
                "S256",
            )
        with pytest.raises(HTTPException, match="Desafio PKCE inválido"):
            rotas_oauth._validar_desafio_pkce("desafio-curto")
    finally:
        app.dependency_overrides.clear()


def test_endpoint_de_revogacao_persiste_pelo_servico(monkeypatch):
    tokens = []
    monkeypatch.setattr(rotas_oauth.service, "revogar", lambda _db, token: (tokens.append(token), {})[1])
    cliente = cliente_teste(monkeypatch)
    try:
        resposta = cliente.post("/v1/oauth/revogar", data={"token": "refresh-opaco"})
        assert resposta.status_code == 200
        assert resposta.json() == {}
        assert tokens == ["refresh-opaco"]
    finally:
        app.dependency_overrides.clear()


def test_revogacao_nao_confirma_sucesso_quando_banco_falha(monkeypatch):
    class BancoComRollback:
        chamadas_rollback = 0

        def rollback(self):
            self.chamadas_rollback += 1

    banco = BancoComRollback()
    app.dependency_overrides[get_db] = lambda: banco

    def falhar(_db, _token):
        raise SQLAlchemyError("banco indisponível")

    monkeypatch.setattr(rotas_oauth.service, "revogar", falhar)
    cliente = cliente_teste(monkeypatch)
    app.dependency_overrides[get_db] = lambda: banco
    try:
        resposta = cliente.post(
            "/v1/oauth/revogar",
            data={"token": "refresh", "token_type_hint": "refresh_token"},
        )
        assert resposta.status_code == 503
        assert resposta.json() == {
            "erro": True,
            "mensagem": "Não foi possível confirmar a revogação",
        }
        assert banco.chamadas_rollback == 1
    finally:
        app.dependency_overrides.clear()


def test_metadados_publicam_apenas_grants_implementados(monkeypatch):
    cliente = cliente_teste(monkeypatch)
    try:
        resposta = cliente.get("/.well-known/oauth-authorization-server")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["response_types_supported"] == ["code"]
        assert corpo["grant_types_supported"] == ["authorization_code", "refresh_token"]
        assert corpo["code_challenge_methods_supported"] == ["S256"]
        assert "client_credentials" not in corpo["grant_types_supported"]
    finally:
        app.dependency_overrides.clear()


def test_metadados_publicam_client_credentials_somente_quando_habilitado(monkeypatch):
    cliente = cliente_teste(monkeypatch)
    monkeypatch.setattr(
        principal,
        "Settings",
        lambda: SimpleNamespace(
            JWT_ISSUER="http://localhost:8001",
            OAUTH_CLIENT_CREDENTIALS_ENABLED=True,
        ),
    )
    try:
        resposta = cliente.get("/.well-known/oauth-authorization-server")
        assert "client_credentials" in resposta.json()["grant_types_supported"]
        assert "client_secret_basic" in resposta.json()["token_endpoint_auth_methods_supported"]
    finally:
        app.dependency_overrides.clear()
