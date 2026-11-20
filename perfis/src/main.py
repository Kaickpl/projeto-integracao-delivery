from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.router import api_router
from src.core.database import get_db
from src.modules.admin.service import (
    AcaoNaoPermitida,
    DadoDuplicado,
    PerfilNaoEncontrado,
)

app = FastAPI(title="Serviço de Perfis")
app.include_router(api_router)


@app.exception_handler(PerfilNaoEncontrado)
async def perfil_nao_encontrado(request: Request, exc: PerfilNaoEncontrado):
    return JSONResponse(status_code=404, content={"detail": "Perfil não encontrado"})


@app.exception_handler(DadoDuplicado)
async def dado_duplicado(request: Request, exc: DadoDuplicado):
    return JSONResponse(
        status_code=409, content={"detail": "CPF/CNPJ ou e-mail já cadastrado"}
    )


@app.exception_handler(AcaoNaoPermitida)
async def acao_nao_permitida(request: Request, exc: AcaoNaoPermitida):
    return JSONResponse(status_code=409, content={"detail": exc.mensagem})


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"database": "ok"}