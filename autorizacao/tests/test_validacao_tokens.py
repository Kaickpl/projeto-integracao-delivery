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
    def __init__(self, papel=None, erro=None, permissoes=None):
        self.papel = papel
        self.erro = erro
        self.permissoes = permissoes or []

    def get(self, _modelo, _conta_id):
        if self.erro:
            raise self.erro
        return self.papel

    def scalars(self, _consulta):
        return SimpleNamespace(all=lambda: self.permissoes)


class BancoEscopos:
    def __init__(self, escopos=None, erro=None):
        self.escopos = escopos or []
        self.erro = erro

    def scalars(self, _consulta):
        if self.erro:
            raise self.erro
        return SimpleNamespace(all=lambda: self.escopos)


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
    banco = BancoFalso(SimpleNamespace(role="LOJA"), permissoes=["loja:operar"])
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
            "permissoes": ["loja:operar"],
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


def test_token_de_servico_e_escopo_atual_sao_validos(monkeypatch):
    app.dependency_overrides[get_db] = lambda: BancoEscopos(["pagamentos:ler"])
    monkeypatch.setattr(
        principal,
        "_decodificar_token_servico",
        lambda token, audiencia: {
            "client_id": "financeiro-worker",
            "escopos": ["pagamentos:ler", "notificacoes:enviar"],
        },
    )
    cliente = TestClient(app)
    try:
        resposta = cliente.post(
            "/v1/tokens/servico/validar",
            headers={"Authorization": "Bearer jwt-servico"},
            json={"audiencia": "https://financeiro.test", "escopos": ["pagamentos:ler"]},
        )
        assert resposta.status_code == 200
        assert resposta.json() == {
            "ativo": True,
            "client_id": "financeiro-worker",
            "audiencia": "https://financeiro.test",
            "escopos": ["pagamentos:ler"],
        }
    finally:
        app.dependency_overrides.clear()


def test_token_de_servico_rejeita_escopo_ausente_ou_revogado(monkeypatch):
    app.dependency_overrides[get_db] = lambda: BancoEscopos(["pagamentos:ler"])
    monkeypatch.setattr(
        principal,
        "_decodificar_token_servico",
        lambda *_: {"client_id": "worker", "escopos": ["pagamentos:ler"]},
    )
    cliente = TestClient(app)
    try:
        nao_no_token = cliente.post(
            "/v1/tokens/servico/validar",
            headers={"Authorization": "Bearer jwt"},
            json={"audiencia": "https://financeiro.test", "escopos": ["pagamentos:escrever"]},
        )
        assert nao_no_token.status_code == 403
        app.dependency_overrides[get_db] = lambda: BancoEscopos([])
        removido_no_rbac = cliente.post(
            "/v1/tokens/servico/validar",
            headers={"Authorization": "Bearer jwt"},
            json={"audiencia": "https://financeiro.test", "escopos": ["pagamentos:ler"]},
        )
        assert removido_no_rbac.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_token_de_servico_trata_jwks_indisponivel_com_503(monkeypatch):
    app.dependency_overrides[get_db] = lambda: BancoEscopos(["pagamentos:ler"])
    monkeypatch.setattr(
        principal,
        "_decodificar_token_servico",
        lambda *_: (_ for _ in ()).throw(principal.PyJWKClientConnectionError("offline")),
    )
    cliente = TestClient(app)
    try:
        resposta = cliente.post(
            "/v1/tokens/servico/validar",
            headers={"Authorization": "Bearer jwt"},
            json={"audiencia": "https://financeiro.test", "escopos": ["pagamentos:ler"]},
        )
        assert resposta.status_code == 503
        assert resposta.json() == {
            "erro": True,
            "mensagem": "Chaves públicas da Identidade indisponíveis",
        }
    finally:
        app.dependency_overrides.clear()


def test_rejeita_jwt_de_usuario_no_validador_de_servico(monkeypatch):
    monkeypatch.setattr(
        principal.jwt,
        "get_unverified_header",
        lambda *_: {"typ": "at+jwt", "alg": "HS256"},
    )
    monkeypatch.setattr(principal, "_cliente_jwks", lambda *_: None)
    assert principal._decodificar_token_servico("token", "https://financeiro.test") is None
