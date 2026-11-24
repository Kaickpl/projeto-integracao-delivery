from fastapi import APIRouter

from src.modules.admin.router import router as admin_router
from src.modules.cliente.router import router as cliente_router
from src.modules.endereco.router import router as endereco_router
from src.modules.entregador.router import router as entregador_router
from src.modules.loja.router import router as loja_router
from src.modules.interno.router import router as interno_router

api_router = APIRouter()
api_router.include_router(admin_router)
api_router.include_router(cliente_router)
api_router.include_router(entregador_router)
api_router.include_router(loja_router)
api_router.include_router(endereco_router)
api_router.include_router(interno_router)
