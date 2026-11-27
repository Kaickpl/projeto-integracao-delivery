from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.router import api_router
from src.core.database import get_db
from src.core.config import settings
from src.core.erros import RESPOSTAS_DE_ERRO, registrar_tratamento_de_erros

app = FastAPI(title="Serviço de Perfis")
origens = [
    origem.strip()
    for origem in settings.CORS_ORIGENS_PERMITIDAS.split(",")
    if origem.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origens,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    allow_credentials=False,
)
app.include_router(api_router, responses=RESPOSTAS_DE_ERRO)
registrar_tratamento_de_erros(app)


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"database": "ok"}
