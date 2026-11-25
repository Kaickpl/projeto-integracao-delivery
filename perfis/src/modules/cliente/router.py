from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.modules.cliente import service
from src.modules.cliente.schemas import ClienteCreate, ClienteResponse

router = APIRouter(prefix="/clientes", tags=["clientes"])


@router.post("", response_model=ClienteResponse, status_code=201)
def cadastrar_cliente(
    dados: ClienteCreate,
    chave_idempotencia: UUID = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    return service.cadastrar_cliente(db, dados, chave_idempotencia)
