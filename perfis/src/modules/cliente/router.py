from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.permissoes import protegida
from src.modules.cliente import service
from src.modules.cliente.schemas import ClienteCreate, ClienteResponse, ClienteUpdate

router = APIRouter(prefix="/clientes", tags=["clientes"])


@router.post("", response_model=ClienteResponse, status_code=201)
def cadastrar_cliente(
    dados: ClienteCreate,
    chave_idempotencia: UUID = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    return service.cadastrar_cliente(db, dados, chave_idempotencia)


@router.get(
    "/{cliente_id}",
    response_model=ClienteResponse,
    **protegida(proprio="perfil:ler_proprio", dono="cliente_id"),
)
def buscar_cliente(cliente_id: UUID, db: Session = Depends(get_db)):
    """Consulta os dados do próprio cliente autenticado."""
    return service.buscar_cliente(db, cliente_id)


@router.patch(
    "/{cliente_id}",
    response_model=ClienteResponse,
    **protegida(proprio="perfil:editar_proprio", dono="cliente_id"),
)
def atualizar_cliente(
    cliente_id: UUID, dados: ClienteUpdate, db: Session = Depends(get_db)
):
    """Altera nome, telefone e endereço do próprio cliente."""
    return service.atualizar_cliente(db, cliente_id, dados)


@router.delete(
    "/{cliente_id}",
    status_code=204,
    **protegida(proprio="perfil:remover_proprio", dono="cliente_id"),
)
def remover_cliente(cliente_id: UUID, db: Session = Depends(get_db)) -> Response:
    """Exclui a própria conta e revoga as sessões associadas."""
    service.remover_cliente(db, cliente_id)
    return Response(status_code=204)
