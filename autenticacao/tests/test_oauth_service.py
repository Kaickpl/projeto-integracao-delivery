from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
import httpx
from fastapi import HTTPException
from pydantic import SecretStr

from src.modules.oauth import service
from src.modules.sessoes.models import CodigoAutorizacao, SessaoRefresh


class FakeDB:
    def __init__(self, registro=None):
        self.registro = registro
        self.resultados_scalar = []
        self.adicionados = []
        self.commits = 0

    def add(self, valor):
        self.adicionados.append(valor)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def scalar(self, _query):
        if self.resultados_scalar:
            return self.resultados_scalar.pop(0)
        return self.registro

    def query(self, _model):
        return self

    def filter(self, *_args):
        return self

    def update(self, *_args, **_kwargs):
        return 1


def test_login_rejeita_credencial_invalida(monkeypatch):
    monkeypatch.setattr(service.RepositorioCredenciais, "buscar_por_email", lambda *_: None)
    with pytest.raises(HTTPException) as erro:
        service.login(FakeDB(), "a@b.com", "senha", "app", "api")
    assert erro.value.status_code == 401


def test_login_valido_consulta_status_e_emite_par(monkeypatch):
    conta_id = uuid4()
    cred = SimpleNamespace(conta_id=conta_id, senha_hash="hash")
    monkeypatch.setattr(service.RepositorioCredenciais, "buscar_por_email", lambda *_: cred)
    monkeypatch.setattr(service, "verificar_senha", lambda *_: True)
    monkeypatch.setattr(service, "obter_status_e_papel", lambda *_: ("ATIVO", "CLIENTE"))
    monkeypatch.setattr(service, "emitir_par", lambda *_: {"access_token": "a", "refresh_token": "r"})
    db = FakeDB()
    assert service.login(db, "a@b.com", "senha", "app", "api")["access_token"] == "a"
    assert db.commits == 1


def test_novo_refresh_persiste_somente_hash(monkeypatch):
    db = FakeDB()
    conta_id = uuid4()
    bruto, registro = service._novo_refresh(db, conta_id, "app", "api")
    assert registro.conta_id == conta_id
    assert registro.token_hash != bruto
    assert len(registro.token_hash) == 64


def test_refresh_desconhecido_retorna_401():
    with pytest.raises(HTTPException) as erro:
        service.renovar(FakeDB(), "desconhecido")
    assert erro.value.status_code == 401


def test_revogar_token_persiste_revogacao_da_familia():
    registro = SimpleNamespace(sessao_id=uuid4(), id=uuid4())
    db = FakeDB()
    db.resultados_scalar = [registro.sessao_id, registro.id]
    assert service.revogar(db, "refresh-valido") == {}
    assert db.commits == 1


def test_revogar_access_token_usa_sessao_e_persiste_familia(monkeypatch):
    sessao_id = uuid4()
    db = FakeDB()
    db.resultados_scalar = [None, uuid4()]
    monkeypatch.setattr(
        service,
        "_decodificar_access_token",
        lambda *_args, **_kwargs: {"sid": str(sessao_id)},
    )
    assert service.revogar(db, "access-token") == {}
    assert db.commits == 1


def test_revogar_token_desconhecido_e_idempotente(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(service, "_decodificar_access_token", lambda *_args, **_kwargs: None)
    assert service.revogar(db, "token-desconhecido") == {}
    assert db.commits == 0


def test_troca_codigo_valida_pkce_e_emite_tokens(monkeypatch):
    verifier = "a" * 43
    import base64, hashlib
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    registro = CodigoAutorizacao(
        id=uuid4(), codigo_hash=hashlib.sha256(b"codigo").hexdigest(),
        conta_id=uuid4(), client_id="app", redirect_uri="https://app.test/callback",
        code_challenge=challenge,
        expira_em=datetime.now(timezone.utc) + timedelta(minutes=1), usado_em=None,
    )
    monkeypatch.setattr(service, "Settings", lambda: SimpleNamespace(
        OAUTH_CLIENT_ID="app", OAUTH_REDIRECT_URI="https://app.test/callback", JWT_AUDIENCE="api"
    ))
    monkeypatch.setattr(service, "obter_status_e_papel", lambda *_: ("ATIVO", "LOJA"))
    monkeypatch.setattr(service, "emitir_par", lambda *_: {"access_token": "ok"})
    db = FakeDB(registro)
    assert service.trocar_codigo(db, "codigo", verifier, "app", "https://app.test/callback")["access_token"] == "ok"
    assert registro.usado_em is not None


def test_introspeccao_retorna_inativo_para_jwt_invalido(monkeypatch):
    monkeypatch.setattr(service, "Settings", lambda: SimpleNamespace(JWT_ISSUER="issuer", JWT_AUDIENCE="api"))
    monkeypatch.setattr(
        service.jwt,
        "get_unverified_header",
        lambda *_: {"kid": "kid", "typ": "at+jwt", "alg": "RS256"},
    )
    monkeypatch.setattr(service, "carregar_chave_publica", lambda *_: object())
    monkeypatch.setattr(service.jwt, "decode", lambda *_args, **_kwargs: (_ for _ in ()).throw(jwt.InvalidTokenError()))
    assert service.introspeccionar(FakeDB(), "invalid") == {"active": False}


def test_introspeccao_ativa_devolve_papel_e_identificadores(monkeypatch):
    conta_id, sessao_id, jti = uuid4(), uuid4(), str(uuid4())
    monkeypatch.setattr(
        service,
        "_decodificar_access_token",
        lambda *_args, **_kwargs: {
            "sub": str(conta_id),
            "sid": str(sessao_id),
            "jti": jti,
            "role": "ENTREGADOR",
        },
    )
    db = FakeDB()
    db.resultados_scalar = [uuid4()]
    assert service.introspeccionar(db, "token") == {
        "active": True,
        "sub": str(conta_id),
        "jti": jti,
        "role": "ENTREGADOR",
    }


def test_decodificador_confere_tipo_assinatura_issuer_e_audience(monkeypatch):
    conta_id, sessao_id = uuid4(), uuid4()
    claims = {
        "sub": str(conta_id),
        "sid": str(sessao_id),
        "jti": str(uuid4()),
        "role": "CLIENTE",
    }
    chamadas = {}
    monkeypatch.setattr(
        service,
        "Settings",
        lambda: SimpleNamespace(JWT_ISSUER="issuer", JWT_AUDIENCE="audiencia"),
    )
    monkeypatch.setattr(
        service.jwt,
        "get_unverified_header",
        lambda *_: {"typ": "at+jwt", "alg": "RS256", "kid": "chave-1"},
    )
    monkeypatch.setattr(service, "carregar_chave_publica", lambda kid: f"publica:{kid}")

    def decodificar(token, chave, **opcoes):
        chamadas.update(token=token, chave=chave, opcoes=opcoes)
        return claims

    monkeypatch.setattr(service.jwt, "decode", decodificar)
    assert service._decodificar_access_token("jwt") == claims
    assert chamadas["chave"] == "publica:chave-1"
    assert chamadas["opcoes"]["algorithms"] == ["RS256"]
    assert chamadas["opcoes"]["issuer"] == "issuer"
    assert chamadas["opcoes"]["audience"] == "audiencia"
    assert chamadas["opcoes"]["options"]["verify_exp"] is True


@pytest.mark.parametrize(
    "header",
    [
        {"typ": "JWT", "alg": "RS256", "kid": "chave-1"},
        {"typ": "at+jwt", "alg": "HS256", "kid": "chave-1"},
    ],
)
def test_decodificador_rejeita_tipo_ou_algoritmo_inesperado(monkeypatch, header):
    monkeypatch.setattr(
        service,
        "Settings",
        lambda: SimpleNamespace(JWT_ISSUER="issuer", JWT_AUDIENCE="audiencia"),
    )
    monkeypatch.setattr(service.jwt, "get_unverified_header", lambda *_: header)
    assert service._decodificar_access_token("jwt") is None


def test_decodificador_permita_validar_assinatura_de_token_expirado_no_logout(monkeypatch):
    conta_id, sessao_id = uuid4(), uuid4()
    chamadas = []
    monkeypatch.setattr(
        service,
        "Settings",
        lambda: SimpleNamespace(JWT_ISSUER="issuer", JWT_AUDIENCE="audiencia"),
    )
    monkeypatch.setattr(
        service.jwt,
        "get_unverified_header",
        lambda *_: {"typ": "at+jwt", "alg": "RS256", "kid": "chave-1"},
    )
    monkeypatch.setattr(service, "carregar_chave_publica", lambda *_: "publica")
    monkeypatch.setattr(
        service.jwt,
        "decode",
        lambda *_args, **kwargs: (
            chamadas.append(kwargs),
            {
                "sub": str(conta_id),
                "sid": str(sessao_id),
                "jti": str(uuid4()),
                "role": "ADMIN",
            },
        )[1],
    )
    assert service._decodificar_access_token("jwt", permitir_expirado=True)["sid"] == str(sessao_id)
    assert chamadas[0]["options"]["verify_exp"] is False


def test_consulta_integrada_busca_status_e_papel(monkeypatch):
    chamadas = []
    monkeypatch.setattr(service, "Settings", lambda: SimpleNamespace(
        PERFIS_URL="http://perfis", PERFIS_STATUS_SERVICE_TOKEN=SecretStr("ps"),
        AUTORIZACAO_URL="http://rbac", AUTORIZACAO_SERVICE_TOKEN=SecretStr("r"),
        INTEGRATION_TIMEOUT_SECONDS=2,
    ))
    respostas = iter([{"status": "ATIVO"}, {"role": "ENTREGADOR"}])
    monkeypatch.setattr(service, "_consultar_servico", lambda *args: (chamadas.append(args), next(respostas))[1])
    assert service.obter_status_e_papel(uuid4()) == ("ATIVO", "ENTREGADOR")
    assert len(chamadas) == 2


def test_consulta_servico_retorna_json_e_trata_erros_de_integracao(monkeypatch):
    monkeypatch.setattr(
        service,
        "Settings",
        lambda: SimpleNamespace(INTEGRATION_TIMEOUT_SECONDS=1),
    )
    monkeypatch.setattr(
        service.httpx,
        "get",
        lambda *_args, **_kwargs: httpx.Response(
            200,
            json={"status": "ATIVO"},
            request=httpx.Request("GET", "http://perfis/status"),
        ),
    )
    assert service._consultar_servico("http://perfis/", "segredo", "/status") == {
        "status": "ATIVO"
    }


@pytest.mark.parametrize("status,codigo", [(404, 403), (500, 503)])
def test_consulta_servico_traduz_status_http(monkeypatch, status, codigo):
    monkeypatch.setattr(
        service,
        "Settings",
        lambda: SimpleNamespace(INTEGRATION_TIMEOUT_SECONDS=1),
    )
    resposta = httpx.Response(
        status,
        request=httpx.Request("GET", "http://perfis/status"),
    )
    monkeypatch.setattr(service.httpx, "get", lambda *_args, **_kwargs: resposta)
    with pytest.raises(HTTPException) as erro:
        service._consultar_servico("http://perfis", "segredo", "/status")
    assert erro.value.status_code == codigo


def test_consulta_servico_trata_timeout_como_503(monkeypatch):
    monkeypatch.setattr(
        service,
        "Settings",
        lambda: SimpleNamespace(INTEGRATION_TIMEOUT_SECONDS=1),
    )
    monkeypatch.setattr(
        service.httpx,
        "get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.TimeoutException("timeout")),
    )
    with pytest.raises(HTTPException) as erro:
        service._consultar_servico("http://perfis", "segredo", "/status")
    assert erro.value.status_code == 503


@pytest.mark.parametrize(
    "status,papel,codigo",
    [("PENDENTE_APROVACAO", "CLIENTE", 403), ("ATIVO", "DONO", 403)],
)
def test_bloqueia_status_pendente_ou_papel_desconhecido(monkeypatch, status, papel, codigo):
    monkeypatch.setattr(service, "Settings", lambda: SimpleNamespace(
        PERFIS_URL="http://perfis", PERFIS_STATUS_SERVICE_TOKEN=SecretStr("ps"),
        AUTORIZACAO_URL="http://rbac", AUTORIZACAO_SERVICE_TOKEN=SecretStr("r"),
        INTEGRATION_TIMEOUT_SECONDS=2,
    ))
    respostas = iter([{"status": status}, {"role": papel}])
    monkeypatch.setattr(service, "_consultar_servico", lambda *_: next(respostas))
    with pytest.raises(HTTPException) as erro:
        service.obter_status_e_papel(uuid4())
    assert erro.value.status_code == codigo


def test_emitir_par_cria_refresh_e_access(monkeypatch):
    conta_id, sessao_id = uuid4(), uuid4()
    monkeypatch.setattr(service, "_novo_refresh", lambda *_args: ("refresh", SimpleNamespace(sessao_id=sessao_id)))
    monkeypatch.setattr(service, "emitir_access_token", lambda *args, **kwargs: (args, kwargs))
    resultado = service.emitir_par(FakeDB(), conta_id, "ADMIN", "app", "api")
    assert resultado["refresh_token"] == "refresh"
    assert resultado["access_token"][1]["sessao_id"] == sessao_id
