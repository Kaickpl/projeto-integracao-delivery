from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

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
        ),
    )
    monkeypatch.setattr(
        principal,
        "Settings",
        lambda: SimpleNamespace(JWT_ISSUER="http://localhost:8001"),
    )
    return TestClient(app, follow_redirects=False)


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
    finally:
        app.dependency_overrides.clear()
