from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.database import get_db

app = FastAPI()


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"database": "ok"}


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}

@app.get("/health")
def health():
    return {"status": "mudei"}