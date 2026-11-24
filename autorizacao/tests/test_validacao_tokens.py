import os
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://teste:teste@localhost:5432/nao_conectar",
)

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError

from src.core.database import get_db
import src.main as principal
from src.main import app


class BancoFalso:
    def __init__(self, papel=None, erro=None):
        self.papel = papel
        self.erro = erro

    def get(self, _modelo, _conta_id):
        if self.erro:
            raise self.erro
        return self.papel


class RespostaFalsa:
    status_code = 200

    def __init__(self, corpo):
        self.corpo = corpo

    def json(self):
        return self.corpo


def preparar_cliente(monkeypatch, banco, introspeccao=None, falha_http=None):
    app.dependency_overrides[get_db] = lambda: banco
    monkeypatch.setattr(
        principal,
        "settings",
        SimpleNamespace(
            AUTHENTICACAO_URL="http://auth-teste",
            AUTHENTICACAO_SERVICE_TOKEN=SecretStr("segredo-servico"),
            INTEGRATION_TIMEOUT_SECONDS=1,
        ),
    )
    chamadas = []

    def post(url, **kwargs):
        chamadas.append((url, kwargs))
        if falha_http:
            raise falha_http
        return RespostaFalsa(introspeccao or {})

    monkeypatch.setattr(principal.httpx, "post", post)
    return TestClient(app), chamadas


def test_token_ativo_e_papel_atual_sao_devolvidos(monkeypatch):
    conta_id, jti = uuid4(), str(uuid4())
    banco = BancoFalso(SimpleNamespace(role="LOJA"))
    cliente, chamadas = preparar_cliente(
        monkeypatch,
        banco,
        {"active": True, "sub": str(conta_id), "jti": jti, "role": "LOJA"},
    )
    try:
        resposta = cliente.post(
            "/v1/tokens/validar",
            headers={"Authorization": "Bearer access-secreto"},
        )
        assert resposta.status_code == 200
        assert resposta.json() == {
            "ativo": True,
            "conta_id": str(conta_id),
            "role": "LOJA",
            "jti": jti,
        }
        assert chamadas[0][0] == "http://auth-teste/v1/oauth/introspeccao"
        assert chamadas[0][1]["json"] == {"token": "access-secreto"}
        assert chamadas[0][1]["headers"]["Authorization"] == "Bearer segredo-servico"
    finally:
        app.dependency_overrides.clear()


def test_token_revogado_ou_sem_bearer_retorna_401_comum(monkeypatch):
    cliente, _ = preparar_cliente(monkeypatch, BancoFalso(), {"active": False})
    try:
        revogado = cliente.post(
            "/v1/tokens/validar",
            headers={"Authorization": "Bearer token-revogado"},
        )
        sem_token = cliente.post("/v1/tokens/validar")
        assert revogado.status_code == sem_token.status_code == 401
        assert revogado.json() == {
            "erro": True,
            "mensagem": "Token inválido, expirado ou revogado",
        }
        assert sem_token.json() == revogado.json()
    finally:
        app.dependency_overrides.clear()


def test_papel_alterado_invalida_claim_antiga(monkeypatch):
    conta_id = uuid4()
    cliente, _ = preparar_cliente(
        monkeypatch,
        BancoFalso(SimpleNamespace(role="ADMIN")),
        {"active": True, "sub": str(conta_id), "jti": "jti", "role": "CLIENTE"},
    )
    try:
        resposta = cliente.post(
            "/v1/tokens/validar", headers={"Authorization": "Bearer token"}
        )
        assert resposta.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_indisponibilidade_do_auth_falha_fechado_com_503(monkeypatch):
    cliente, _ = preparar_cliente(
        monkeypatch,
        BancoFalso(),
        falha_http=httpx.ConnectError("indisponível"),
    )
    try:
        resposta = cliente.post(
            "/v1/tokens/validar", headers={"Authorization": "Bearer token"}
        )
        assert resposta.status_code == 503
        assert resposta.json() == {
            "erro": True,
            "mensagem": "Serviço de Identidade indisponível",
        }
    finally:
        app.dependency_overrides.clear()


def test_indisponibilidade_do_banco_rbac_retorna_503(monkeypatch):
    cliente, _ = preparar_cliente(
        monkeypatch,
        BancoFalso(erro=SQLAlchemyError("banco indisponível")),
        {"active": True, "sub": str(uuid4()), "jti": "jti", "role": "CLIENTE"},
    )
    try:
        resposta = cliente.post(
            "/v1/tokens/validar", headers={"Authorization": "Bearer token"}
        )
        assert resposta.status_code == 503
        assert resposta.json() == {
            "erro": True,
            "mensagem": "Serviço de Autorização indisponível",
        }
    finally:
        app.dependency_overrides.clear()


def test_openapi_documenta_respostas_de_validacao():
    respostas = TestClient(app).get("/openapi.json").json()["paths"][
        "/v1/tokens/validar"
    ]["post"]["responses"]
    assert "200" in respostas
    assert "401" in respostas
    assert "503" in respostas
