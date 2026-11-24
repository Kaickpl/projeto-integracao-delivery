from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.modules.cliente import service
from src.modules.cliente.schemas import ClienteCreate, ClienteResponse

router = APIRouter(prefix="/clientes", tags=["clientes"])


@router.post("", response_model=ClienteResponse, status_code=201)
def cadastrar_cliente(dados: ClienteCreate, db: Session = Depends(get_db)):
    return service.cadastrar_cliente(db, dados)
