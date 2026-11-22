from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.router import api_router
from src.core.database import get_db
from src.core.erros import RESPOSTAS_DE_ERRO, registrar_tratamento_de_erros

app = FastAPI(title="Serviço de Perfis")
app.include_router(api_router, responses=RESPOSTAS_DE_ERRO)
registrar_tratamento_de_erros(app)


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"database": "ok"}
