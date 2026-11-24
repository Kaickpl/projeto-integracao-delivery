import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from psycopg.errors import UniqueViolation
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from src.core.database import SCHEMA_AUTENTICACAO, get_db, obter_fabrica_sessoes
from src.core.security import verificar_senha
from src.modules.credenciais.repository import RepositorioCredenciais


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
