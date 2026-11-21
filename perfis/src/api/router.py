from fastapi import APIRouter

from src.modules.admin.router import router as admin_router
from src.modules.entregador.router import router as entregador_router

api_router = APIRouter()
api_router.include_router(admin_router)
api_router.include_router(entregador_router)
