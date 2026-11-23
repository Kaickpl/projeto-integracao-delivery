import re
from datetime import date
from typing import Annotated

from pydantic import AfterValidator, Field


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


def limpar_placa(valor: str) -> str:
    return re.sub(r"[-\s]", "", valor).upper()


def placa_valida(placa: str) -> bool:
    return re.fullmatch(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}", placa) is not None


def cnh_valida(cnh: str) -> bool:
    return re.fullmatch(r"[0-9]{11}", cnh) is not None


UFS = frozenset({
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE",
    "TO",
})


def limpar_cep(valor: str) -> str:
    return re.sub(r"[.\-\s]", "", valor)


def cep_valido(cep: str) -> bool:
    return re.fullmatch(r"[0-9]{8}", cep) is not None


def uf_valida(uf: str) -> bool:
    return uf in UFS


IDADE_MINIMA = 18
IDADE_MAXIMA = 120


def calcular_idade(nascimento: date, hoje: date | None = None) -> int:
    """Anos completos na data de hoje.

    Quem nasceu em 29/02 completa ano em 01/03 nos anos que não são bissextos.
    """
    hoje = hoje or date.today()
    ja_fez_aniversario = (hoje.month, hoje.day) >= (nascimento.month, nascimento.day)
    return hoje.year - nascimento.year - (0 if ja_fez_aniversario else 1)


def validar_maioridade(nascimento: date) -> date:
    if nascimento > date.today():
        raise ValueError("Data de nascimento no futuro")
    idade = calcular_idade(nascimento)
    if idade > IDADE_MAXIMA:
        raise ValueError("Data de nascimento inválida")
    if idade < IDADE_MINIMA:
        raise ValueError(f"É preciso ter pelo menos {IDADE_MINIMA} anos para se cadastrar")
    return nascimento


# Campo dos schemas de cadastro: data no formato AAAA-MM-DD, 18 anos ou mais.
DataNascimento = Annotated[
    date,
    AfterValidator(validar_maioridade),
    Field(description="AAAA-MM-DD. Precisa ter 18 anos ou mais", examples=["1995-08-20"]),
]
