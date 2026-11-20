import re


def limpar_documento(valor: str) -> str:
    """Remove pontuação e deixa em maiúsculas (mantém as letras do CNPJ novo)."""
    return re.sub(r"[.\-/\s]", "", valor).upper()


def cpf_valido(cpf: str) -> bool:
    if not re.fullmatch(r"[0-9]{11}", cpf) or cpf == cpf[0] * 11:
        return False
    for posicao in (9, 10):
        soma = sum(int(cpf[i]) * (posicao + 1 - i) for i in range(posicao))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[posicao]):
            return False
    return True


def cnpj_valido(cnpj: str) -> bool:
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", cnpj) or cnpj == cnpj[0] * 14:
        return False
    pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for posicao, pesos_atuais in ((12, pesos), (13, [6] + pesos)):
        soma = sum((ord(c) - 48) * p for c, p in zip(cnpj, pesos_atuais))
        resto = soma % 11
        digito = 0 if resto < 2 else 11 - resto
        if digito != int(cnpj[posicao]):
            return False
    return True


def documento_valido(documento: str) -> bool:
    return cpf_valido(documento) or cnpj_valido(documento)