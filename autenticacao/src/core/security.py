from pwdlib import PasswordHash
from pwdlib.exceptions import HashVerificationError, UnknownHashError

_gerenciador_hash = PasswordHash.recommended()


def gerar_hash_senha(senha: str) -> str:
    return _gerenciador_hash.hash(senha)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    try:
        return _gerenciador_hash.verify(senha, senha_hash)
    except (UnknownHashError, HashVerificationError):
        return False
