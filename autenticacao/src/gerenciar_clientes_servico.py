"""Provisiona clientes M2M; o segredo gerado é exibido uma única vez."""
import argparse
import re
import secrets

from sqlalchemy.exc import IntegrityError

from src.core.database import obter_fabrica_sessoes
from src.modules.clientes_servico.repository import RepositorioClientesServico


def executar() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcomandos = parser.add_subparsers(dest="acao", required=True)
    criar = subcomandos.add_parser("criar")
    criar.add_argument("client_id")
    rotacionar = subcomandos.add_parser("rotacionar")
    rotacionar.add_argument("client_id")
    desativar = subcomandos.add_parser("desativar")
    desativar.add_argument("client_id")
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9._~-]{1,120}", args.client_id):
        parser.error("client_id deve conter de 1 a 120 caracteres OAuth seguros")

    with obter_fabrica_sessoes()() as db:
        repositorio = RepositorioClientesServico(db)
        cliente = repositorio.buscar_para_gestao(args.client_id)
        if args.acao == "criar":
            if cliente is not None:
                parser.error("client_id já cadastrado")
            segredo = secrets.token_urlsafe(48)
            try:
                repositorio.criar(args.client_id, segredo)
                db.commit()
            except IntegrityError:
                db.rollback()
                parser.error("client_id já cadastrado")
            print(f"client_id: {args.client_id}")
            print(f"client_secret (exibido uma única vez): {segredo}")
            return 0

        if cliente is None:
            parser.error("cliente não encontrado")
        if args.acao == "rotacionar":
            segredo = secrets.token_urlsafe(48)
            repositorio.trocar_segredo(cliente, segredo)
            db.commit()
            print(f"client_id: {args.client_id}")
            print(f"novo client_secret (exibido uma única vez): {segredo}")
            return 0

        repositorio.desativar(cliente)
        db.commit()
        print(f"Cliente {args.client_id} desativado")
        return 0


if __name__ == "__main__":
    raise SystemExit(executar())
