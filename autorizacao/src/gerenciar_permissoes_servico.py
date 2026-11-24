"""Concede ou remove escopos M2M no RBAC por operação administrativa local."""
import argparse
import re

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from src.core.database import SessionLocal
from src.modules.papeis import PermissaoClienteServico


def executar() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcomandos = parser.add_subparsers(dest="acao", required=True)
    for acao in ("conceder", "remover"):
        comando = subcomandos.add_parser(acao)
        comando.add_argument("client_id")
        comando.add_argument("audiencia")
        comando.add_argument("escopos", nargs="+")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9._~-]{1,120}", args.client_id):
        parser.error("client_id inválido")
    if any(not re.fullmatch(r"[!-~]+", escopo) or '"' in escopo or "\\" in escopo for escopo in args.escopos):
        parser.error("escopo OAuth inválido")

    with SessionLocal() as db:
        if args.acao == "conceder":
            for escopo in set(args.escopos):
                db.execute(
                    insert(PermissaoClienteServico)
                    .values(
                        client_id=args.client_id,
                        audiencia=args.audiencia,
                        escopo=escopo,
                    )
                    .on_conflict_do_nothing()
                )
        else:
            db.execute(
                delete(PermissaoClienteServico).where(
                    PermissaoClienteServico.client_id == args.client_id,
                    PermissaoClienteServico.audiencia == args.audiencia,
                    PermissaoClienteServico.escopo.in_(set(args.escopos)),
                )
            )
        db.commit()
    verbo = "concedidas" if args.acao == "conceder" else "removidas"
    print(f"Permissões {verbo} para {args.client_id} atualizadas")
    return 0


if __name__ == "__main__":
    raise SystemExit(executar())
