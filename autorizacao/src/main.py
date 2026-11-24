import secrets
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.database import get_db, settings
from src.modules.papeis import PapelConta

PAPEIS = {"CLIENTE", "LOJA", "ENTREGADOR", "ADMIN"}


def autenticar(authorization: str | None, segredo: str) -> None:
    valor = authorization.removeprefix("Bearer ") if authorization else ""
    if not segredo or not secrets.compare_digest(valor, segredo):
        raise HTTPException(401, "Credencial de serviço inválida")


def autenticar_perfis(authorization: str | None = Header(default=None)) -> None:
    autenticar(authorization, settings.INTERNAL_SERVICE_TOKEN.get_secret_value())


def autenticar_auth(authorization: str | None = Header(default=None)) -> None:
    autenticar(authorization, settings.AUTHENTICACAO_SERVICE_TOKEN.get_secret_value())


app = FastAPI(title="Serviço de Autorização e RBAC")


class PapelEntrada(BaseModel):
    role: str


@app.get("/v1/interno/contas/{conta_id}/papel")
def consultar_papel(
    conta_id: UUID,
    _auth: None = Depends(autenticar_auth),
    db: Session = Depends(get_db),
):
    papel = db.get(PapelConta, conta_id)
    if papel is None:
        raise HTTPException(404, "Papel não associado")
    return {"conta_id": str(papel.conta_id), "role": papel.role}


@app.put("/v1/interno/contas/{conta_id}/papel")
def associar_papel(
    conta_id: UUID,
    dados: PapelEntrada,
    _auth: None = Depends(autenticar_perfis),
    db: Session = Depends(get_db),
):
    if dados.role not in PAPEIS:
        raise HTTPException(400, "Papel inválido")
    papel = db.get(PapelConta, conta_id)
    if papel is None:
        papel = PapelConta(conta_id=conta_id, role=dados.role)
        db.add(papel)
    else:
        papel.role = dados.role
    db.commit()
    return {"conta_id": str(conta_id), "role": dados.role}


@app.get("/health")
def health():
    return {"status": "ok"}
