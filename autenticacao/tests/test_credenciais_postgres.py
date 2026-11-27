import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg.errors import UniqueViolation
from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from src.core.database import SCHEMA_AUTENTICACAO, get_db, obter_fabrica_sessoes
from src.core.security import verificar_senha
from src.main import app
from src.modules.credenciais.models import Credencial
from src.modules.credenciais.repository import RepositorioCredenciais
from src.modules.oauth import service
from src.modules.sessoes.models import CodigoAutorizacao, SessaoRefresh


@pytest.fixture(scope="module")
def banco_migrado():
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Defina TEST_DATABASE_URL para o PostgreSQL local descartável")

    url = make_url(dsn)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"127.0.0.1", "::1"}
        or not (url.database or "").startswith("auth_teste")
        or url.query
    ):
        pytest.fail("Use um banco local descartável com nome começando por auth_teste")

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with pytest.MonkeyPatch.context() as ambiente:
        ambiente.setenv("DATABASE_URL", dsn)
        obter_fabrica_sessoes.cache_clear()
        fabrica_a = obter_fabrica_sessoes()
        obter_fabrica_sessoes.cache_clear()
        fabrica_b = obter_fabrica_sessoes()
        engine = fabrica_a.kw["bind"]
        try:
            assert not inspect(engine).has_table("credenciais", schema=SCHEMA_AUTENTICACAO)
            command.upgrade(config, "head")
            try:
                yield config, fabrica_a, fabrica_b
            finally:
                command.downgrade(config, "base")
                assert not inspect(engine).has_table("credenciais", schema=SCHEMA_AUTENTICACAO)
        finally:
            engine.dispose()
            fabrica_b.kw["bind"].dispose()
            obter_fabrica_sessoes.cache_clear()


def test_migracao_cria_tabela_e_historico_isolado(banco_migrado):
    config, fabrica, _ = banco_migrado
    with fabrica.begin() as sessao:
        tabelas = inspect(sessao.connection())
        assert set(tabelas.get_table_names(schema=SCHEMA_AUTENTICACAO)) == {
            "credenciais",
            "sessoes_refresh",
            "codigos_autorizacao",
            "clientes_servico",
            "alembic_version",
        }
        assert not tabelas.get_table_names()
        assert not tabelas.has_schema("auth")
        sessao.execute(text("CREATE TABLE public.alembic_version (version_num text NOT NULL)"))
        sessao.execute(text("INSERT INTO public.alembic_version VALUES ('revisao-de-perfis')"))

    try:
        command.upgrade(config, "head")
        command.check(config)
        with fabrica() as sessao:
            assert sessao.scalar(text("SELECT version_num FROM public.alembic_version")) == (
                "revisao-de-perfis"
            )
    finally:
        with fabrica.begin() as sessao:
            sessao.execute(text("DROP TABLE public.alembic_version"))


def test_api_provisiona_idempotentemente_e_recusa_dados_invalidos(banco_migrado, monkeypatch, caplog):
    _, fabrica, _ = banco_migrado
    monkeypatch.setenv("PERFIS_SERVICE_TOKEN", "teste-perfis-auth")
    dados = {
        "conta_id": str(uuid4()),
        "email": f"{uuid4().hex}@example.com",
        "senha": "Senha-exclusiva-do-teste",
        "tipo_conta": "CLIENTE",
    }
    rota = "/v1/interno/credenciais"
    headers = {"Authorization": "Bearer teste-perfis-auth"}
    with TestClient(app) as cliente:
        recusas = [
            cliente.post(rota, json=dados),
            cliente.post(rota, json=dados, headers={"Authorization": "teste-perfis-auth"}),
            cliente.post(rota, json=dados, headers={"Authorization": "Bearer errado"}),
            cliente.post(rota, json={**dados, "tipo_conta": "OUTRO"}, headers=headers),
            cliente.post(rota, json={**dados, "email": "sem-arroba"}, headers=headers),
        ]
        assert [resposta.status_code for resposta in recusas] == [401, 401, 401, 400, 422]
        with fabrica() as sessao:
            assert RepositorioCredenciais(sessao).buscar_por_email(dados["email"]) is None

        criada = cliente.post(rota, json=dados, headers=headers)
        repetida = cliente.post(rota, json=dados, headers=headers)
        divergente = cliente.post(rota, json={**dados, "senha": "Outra-senha"}, headers=headers)
        assert [criada.status_code, repetida.status_code, divergente.status_code] == [201, 200, 409]
        assert criada.json() == repetida.json() == {"conta_id": dados["conta_id"]}

    with fabrica() as sessao:
        credencial = RepositorioCredenciais(sessao).buscar_por_email(dados["email"])
        senha_hash = credencial.senha_hash
        assert senha_hash.startswith("$argon2id$")
        assert verificar_senha(dados["senha"], senha_hash)
    for resposta in [*recusas, criada, repetida, divergente]:
        assert dados["senha"] not in resposta.text
        assert senha_hash not in resposta.text
    assert dados["senha"] not in caplog.text
    assert senha_hash not in caplog.text


def test_api_provisiona_uma_credencial_sob_concorrencia(banco_migrado, monkeypatch):
    _, fabrica, _ = banco_migrado
    monkeypatch.setenv("PERFIS_SERVICE_TOKEN", "teste-perfis-auth")
    email = f"{uuid4().hex}@example.com"
    barreira = Barrier(2)

    def provisionar(endereco):
        with TestClient(app) as cliente:
            barreira.wait(timeout=5)
            return cliente.post(
                "/v1/interno/credenciais",
                headers={"Authorization": "Bearer teste-perfis-auth"},
                json={
                    "conta_id": str(uuid4()),
                    "email": endereco,
                    "senha": "Senha-do-teste",
                    "tipo_conta": "CLIENTE",
                },
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(provisionar, (email, email.upper()))) == [201, 409]
    with fabrica() as sessao:
        assert sessao.scalar(
            select(func.count()).select_from(Credencial).where(func.lower(Credencial.email) == email)
        ) == 1


@pytest.mark.parametrize("status_perfis,pronta,codigo", [
    ("PENDENTE_APROVACAO", True, 403),
    ("SUSPENSO", True, 403),
    ("ATIVO", False, 403),
    ("ATIVO", None, 503),
    (None, None, 503),
])
def test_login_recusado_nao_grava_codigo_ou_sessao(
    banco_migrado, monkeypatch, status_perfis, pronta, codigo,
):
    _, fabrica, _ = banco_migrado
    conta_id = uuid4()
    email = f"{uuid4().hex}@example.com"
    senha = "Senha-do-teste"
    with fabrica.begin() as sessao:
        RepositorioCredenciais(sessao).criar(conta_id, email, senha)

    def consultar_perfis(url, **kwargs):
        assert url.endswith(f"/contas/{conta_id}/status")
        if status_perfis is None:
            raise httpx.ReadTimeout("timeout simulado")
        dados = {"conta_id": str(conta_id), "status": status_perfis}
        if pronta is not None:
            dados["identidade_pronta"] = pronta
        return httpx.Response(200, json=dados, request=httpx.Request("GET", url))

    monkeypatch.setattr(service.httpx, "get", consultar_perfis)
    monkeypatch.setenv("OAUTH_CLIENT_ID", "delivery-app")
    monkeypatch.setenv("OAUTH_REDIRECT_URI", "http://localhost:3000/oauth/callback")
    with TestClient(app, follow_redirects=False) as cliente:
        recusado = cliente.post(
            "/v1/oauth/entrar",
            data={
                "email": email,
                "senha": senha,
                "client_id": "delivery-app",
                "redirect_uri": "http://localhost:3000/oauth/callback",
                "response_type": "code",
                "code_challenge": "a" * 43,
                "code_challenge_method": "S256",
                "state": "estado-do-teste",
            },
        )
    assert recusado.status_code == codigo
    assert "location" not in recusado.headers
    with fabrica() as sessao:
        assert sessao.scalar(select(CodigoAutorizacao).where(CodigoAutorizacao.conta_id == conta_id)) is None
        assert sessao.scalar(select(SessaoRefresh).where(SessaoRefresh.conta_id == conta_id)) is None


def test_janela_deslizante_expira_e_login_limpa_historico(banco_migrado, monkeypatch):
    _, fabrica, _ = banco_migrado
    agora = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "_hora_decisao", lambda _: agora)
    monkeypatch.setattr(service, "obter_status_e_papel", lambda _: ("ATIVO", "CLIENTE"))
    monkeypatch.setenv("OAUTH_CLIENT_ID", "delivery-app")
    monkeypatch.setenv("OAUTH_REDIRECT_URI", "http://localhost:3000/oauth/callback")
    conta_id = uuid4()
    email = f"{uuid4().hex}@example.com"
    senha = "Senha-do-teste"
    with fabrica.begin() as sessao:
        RepositorioCredenciais(sessao).criar(conta_id, email, senha)

    def login(cliente, senha_enviada):
        return cliente.post("/v1/oauth/entrar", data={
            "email": email,
            "senha": senha_enviada,
            "client_id": "delivery-app",
            "redirect_uri": "http://localhost:3000/oauth/callback",
            "response_type": "code",
            "code_challenge": "a" * 43,
            "code_challenge_method": "S256",
            "state": "estado-do-teste",
        })

    with TestClient(app, follow_redirects=False) as cliente:
        assert login(cliente, "senha-errada").status_code == 401
        agora += timedelta(minutes=15)
        for _ in range(4):
            assert login(cliente, "senha-errada").status_code == 401
        with fabrica() as sessao:
            credencial = sessao.get(Credencial, conta_id)
            assert credencial.falhas_login == [agora] * 4
            assert credencial.login_bloqueado_ate is None
        assert login(cliente, "senha-errada").status_code == 401
        prazo = agora + timedelta(minutes=15)
        agora = prazo - timedelta(microseconds=1)
        bloqueada = login(cliente, senha)
        assert bloqueada.status_code == 401
        assert bloqueada.json() == {"detail": "Usuário ou senha inválidos"}
        with fabrica() as sessao:
            credencial = sessao.get(Credencial, conta_id)
            assert credencial.login_bloqueado_ate == prazo
            assert len(credencial.falhas_login) == 5
            assert sessao.scalar(select(CodigoAutorizacao).where(CodigoAutorizacao.conta_id == conta_id)) is None

        agora = prazo
        assert login(cliente, senha).status_code == 303
        assert login(cliente, "senha-errada").status_code == 401
        assert login(cliente, senha).status_code == 303
        with fabrica() as sessao:
            credencial = sessao.get(Credencial, conta_id)
            assert credencial.login_bloqueado_ate is None
            assert credencial.falhas_login == []


def test_persiste_e_recupera_apenas_o_hash_da_senha(banco_migrado, caplog):
    conta_id = uuid4()
    senha = "senha-sintetica-que-nunca-deve-ir-ao-banco"
    caplog.set_level(logging.INFO, logger="sqlalchemy.engine")
    with contextmanager(get_db)() as sessao:
        with sessao.begin():
            repositorio = RepositorioCredenciais(sessao)
            primeira = repositorio.criar(conta_id, " Pessoa@example.test ", senha)
            segunda = repositorio.criar(uuid4(), "outro@example.test", senha)
            assert primeira.senha_hash != segunda.senha_hash

    with contextmanager(get_db)() as sessao:
        repositorio = RepositorioCredenciais(sessao)
        credencial = repositorio.buscar_por_email("pessoa@EXAMPLE.TEST")
        assert credencial is not None
        assert credencial.conta_id == conta_id
        assert repositorio.buscar_por_conta_id(conta_id) is credencial
        assert credencial.email == "Pessoa@example.test"
        assert credencial.criado_em.utcoffset() is not None
        assert credencial.atualizado_em == credencial.criado_em
        assert senha not in credencial.senha_hash
        assert verificar_senha(senha, credencial.senha_hash)
        assert not verificar_senha("outra-senha", credencial.senha_hash)

    assert "INSERT INTO autenticacao.credenciais" in caplog.text
    assert senha not in caplog.text
    assert "$argon2id$" not in caplog.text


def test_duas_instancias_concorrentes_rejeitam_email_duplicado(banco_migrado):
    _, fabrica_a, fabrica_b = banco_migrado
    assert fabrica_a.kw["bind"] is not fabrica_b.kw["bind"]
    sincronizar = Barrier(2, timeout=10)

    def registrar(fabrica, email):
        try:
            with fabrica.begin() as sessao:
                sessao.execute(text("SET LOCAL statement_timeout = '10s'"))
                conexao = sessao.scalar(text("SELECT pg_backend_pid()"))
                sincronizar.wait()
                RepositorioCredenciais(sessao).criar(uuid4(), email, "senha-sintetica")
        except IntegrityError as erro:
            assert isinstance(erro.orig, UniqueViolation)
            assert erro.orig.diag.constraint_name == "uq_credenciais_email"
            return conexao, False
        return conexao, True

    with ThreadPoolExecutor(max_workers=2) as executor:
        a = executor.submit(registrar, fabrica_a, "concorrente@example.test")
        b = executor.submit(registrar, fabrica_b, "CONCORRENTE@example.test")
        (conexao_a, sucesso_a), (conexao_b, sucesso_b) = a.result(), b.result()
    assert conexao_a != conexao_b
    assert sucesso_a != sucesso_b
    with fabrica_b() as sessao:
        assert RepositorioCredenciais(sessao).buscar_por_email("concorrente@example.test")
