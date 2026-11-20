import pytest

from src.core.security import gerar_hash_senha, verificar_senha


def test_argon2id_valida_a_senha_e_gera_um_hash_diferente_a_cada_vez():
    senha = "senha sintética longa com acentuação"
    senha_hash = gerar_hash_senha(senha)

    assert senha_hash.startswith("$argon2id$")
    assert senha not in senha_hash
    assert senha_hash != gerar_hash_senha(senha)
    assert verificar_senha(senha, senha_hash)
    assert not verificar_senha(senha + "!", senha_hash)


@pytest.mark.parametrize("senha_hash", ["formato-desconhecido", "$argon2id$v=19$m=65536,t=3,p=4"])
def test_rejeita_hash_invalido(senha_hash):
    assert not verificar_senha("senha sintética", senha_hash)
