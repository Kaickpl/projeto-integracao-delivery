"""Cria o primeiro ADMIN por operação administrativa local.

`POST /admin/admins` exige um ADMIN autenticado, então o primeiro precisa ser
criado por aqui. Auth e RBAC precisam estar no ar, porque o cadastro cria a
credencial no Auth e associa o papel no RBAC.

    python -m src.criar_admin_inicial --nome "Nome" --email admin@exemplo.com \\
        --cpf 00000000000 --telefone 81999990000 --data-nascimento 1990-01-31

A senha vem de ADMIN_INICIAL_SENHA ou é pedida no terminal, sem eco. Se já
existir um ADMIN ativo, nada é feito. Se o provisionamento falhar no meio,
repita o comando com os mesmos dados e a --chave-idempotencia exibida.
"""
import argparse
import getpass
import os
import sys
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select

from src.core.database import SessionLocal
from src.core.exceptions import ErroDeNegocio
from src.modules.admin import service
from src.modules.admin.schemas import AdminCreate
from src.modules.perfil_usuario.perfil import Perfil, TipoPerfil


def executar() -> int:
    parser = argparse.ArgumentParser(description="Cria o primeiro ADMIN.")
    parser.add_argument("--nome", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--cpf", required=True, help="CPF ou CNPJ, com ou sem pontuação")
    parser.add_argument("--telefone", required=True)
    parser.add_argument("--data-nascimento", required=True, help="AAAA-MM-DD")
    parser.add_argument(
        "--chave-idempotencia",
        type=UUID,
        help="Use a chave exibida numa tentativa anterior para retomar o cadastro",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        ja_existe = db.scalar(
            select(Perfil.id)
            .where(Perfil.tipo == TipoPerfil.ADMIN, Perfil.identidade_pronta.is_(True))
            .limit(1)
        )
        if ja_existe is not None:
            print("Já existe um ADMIN ativo; nenhum foi criado. Use POST /admin/admins.")
            return 0

        senha = os.environ.get("ADMIN_INICIAL_SENHA") or getpass.getpass("Senha do ADMIN: ")
        try:
            dados = AdminCreate(
                nome=args.nome,
                cpf_cnpj=args.cpf,
                email=args.email,
                senha=senha,
                telefone=args.telefone,
                data_nascimento=args.data_nascimento,
            )
        except ValidationError as exc:
            # Só campo e motivo: a mensagem padrão repetiria a senha digitada.
            for erro in exc.errors():
                campo = ".".join(str(parte) for parte in erro["loc"])
                print(f"{campo}: {erro['msg'].removeprefix('Value error, ')}", file=sys.stderr)
            return 2

        chave = args.chave_idempotencia or uuid4()
        try:
            admin = service.criar_admin(db, dados, chave)
        except ErroDeNegocio as exc:
            print(f"Erro: {exc.mensagem}", file=sys.stderr)
            print(
                f"Para retomar, repita o comando com --chave-idempotencia {chave}",
                file=sys.stderr,
            )
            return 1
        print(f"ADMIN criado: {admin.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(executar())
