from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.core import tokens


@pytest.fixture
def chave_configurada(tmp_path, monkeypatch):
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    caminho = tmp_path / "jwt-private.pem"
    caminho.write_bytes(
        chave.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    monkeypatch.setattr(
        tokens,
        "Settings",
        lambda: SimpleNamespace(
            JWT_PRIVATE_KEY_PATH=caminho,
            JWT_OLD_PUBLIC_KEYS_DIR=tmp_path / "anteriores",
            JWT_KEY_ID="teste-1",
            JWT_ISSUER="https://identidade.test",
            JWT_ACCESS_TOKEN_MINUTES=25,
            OAUTH_SERVICE_TOKEN_MINUTES=10,
        ),
    )
    tokens._carregar_chave_privada.cache_clear()
    yield chave, caminho
    tokens._carregar_chave_privada.cache_clear()


def test_emitir_access_token_assinado_com_claims_e_expiracao(chave_configurada):
    chave, _ = chave_configurada
    agora = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
    conta_id = uuid4()

    token = tokens.emitir_access_token(
        conta_id,
        "CLIENTE",
        "catalogo",
        "aplicativo-cliente",
        agora=agora,
    )

    claims = jwt.decode(
        token,
        chave.public_key(),
        algorithms=["RS256"],
        audience="catalogo",
        issuer="https://identidade.test",
        options={"verify_exp": False},
    )
    cabecalho = jwt.get_unverified_header(token)
    assert claims["sub"] == str(conta_id)
    assert claims["role"] == "CLIENTE"
    assert claims["client_id"] == "aplicativo-cliente"
    assert claims["exp"] - claims["iat"] == 25 * 60
    assert cabecalho["kid"] == "teste-1"
    assert cabecalho["typ"] == "at+jwt"


def test_token_de_servico_nao_contem_role_ou_sessao(chave_configurada):
    chave, _ = chave_configurada
    agora = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
    token = tokens.emitir_access_token_servico(
        "financeiro-worker",
        "https://financeiro.test",
        ["pagamentos:ler", "notificacoes:enviar"],
        agora=agora,
    )
    claims = jwt.decode(
        token,
        chave.public_key(),
        algorithms=["RS256"],
        audience="https://financeiro.test",
        issuer="https://identidade.test",
        options={"verify_exp": False},
    )
    assert claims["sub"] == "servico:financeiro-worker"
    assert claims["client_id"] == "financeiro-worker"
    assert claims["scope"] == "notificacoes:enviar pagamentos:ler"
    assert claims["exp"] - claims["iat"] == 10 * 60
    assert "role" not in claims
    assert "sid" not in claims


def test_jwks_publica_apenas_chave_publica(chave_configurada):
    chave, _ = chave_configurada

    documento = tokens.documento_jwks()

    assert len(documento["keys"]) == 1
    jwk = documento["keys"][0]
    assert jwk["kid"] == "teste-1"
    assert jwk["alg"] == "RS256"
    assert jwk["use"] == "sig"
    assert "n" in jwk and "e" in jwk
    assert "d" not in jwk
    token = tokens.emitir_access_token(uuid4(), "LOJA", "catalogo", "cliente")
    assert jwt.decode(
        token,
        jwt.algorithms.RSAAlgorithm.from_jwk(__import__("json").dumps(jwk)),
        algorithms=["RS256"],
        audience="catalogo",
        issuer="https://identidade.test",
        options={"verify_exp": False},
    )["role"] == "LOJA"


def test_rejeita_chave_rsa_menor_que_2048_bits(tmp_path):
    chave = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    caminho = tmp_path / "fraca.pem"
    caminho.write_bytes(
        chave.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    tokens._carregar_chave_privada.cache_clear()
    with pytest.raises(ValueError, match="2048"):
        tokens._carregar_chave_privada(str(caminho), caminho.stat().st_mtime_ns)
    tokens._carregar_chave_privada.cache_clear()


def test_rejeita_chave_que_nao_e_rsa(tmp_path):
    from cryptography.hazmat.primitives.asymmetric import ed25519

    chave = ed25519.Ed25519PrivateKey.generate()
    caminho = tmp_path / "nao-rsa.pem"
    caminho.write_bytes(
        chave.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    tokens._carregar_chave_privada.cache_clear()
    with pytest.raises(ValueError, match="RSA"):
        tokens._carregar_chave_privada(str(caminho), caminho.stat().st_mtime_ns)
    tokens._carregar_chave_privada.cache_clear()


def test_jwks_publica_chave_atual_e_chave_anterior(chave_configurada):
    _, caminho = chave_configurada
    antigas = caminho.parent / "anteriores"
    antigas.mkdir()
    chave_antiga = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (antigas / "chave-antiga.pem").write_bytes(
        chave_antiga.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    documento = tokens.documento_jwks()

    assert {chave["kid"] for chave in documento["keys"]} == {"teste-1", "chave-antiga"}
    assert all("d" not in chave for chave in documento["keys"])


def test_carregar_chave_publica_localiza_kid_atual_e_anterior(chave_configurada):
    chave_atual, caminho = chave_configurada
    antigas = caminho.parent / "anteriores"
    antigas.mkdir()
    chave_antiga = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    arquivo_antigo = antigas / "chave-antiga.pem"
    arquivo_antigo.write_bytes(
        chave_antiga.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    assert tokens.carregar_chave_publica("teste-1").public_numbers() == chave_atual.public_key().public_numbers()
    assert tokens.carregar_chave_publica("chave-antiga").public_numbers() == chave_antiga.public_key().public_numbers()
