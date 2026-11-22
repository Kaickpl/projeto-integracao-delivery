"""Formato de erro combinado pela turma: {"erro": true, "mensagem": "..."}.

Todas as respostas de erro do serviço passam por aqui, inclusive as que o
próprio FastAPI gera (rota inexistente, método errado, validação).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.exceptions import ErroDeNegocio

logger = logging.getLogger(__name__)


class ErroResponse(BaseModel):
    erro: bool = True
    mensagem: str


# Usado no OpenAPI no lugar do erro de validação padrão do FastAPI.
RESPOSTAS_DE_ERRO = {
    422: {"model": ErroResponse, "description": "Dados inválidos"},
}


def resposta_de_erro(
    status_code: int, mensagem: str, headers: dict | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"erro": True, "mensagem": mensagem},
        headers=headers,
    )


def _descrever_erros_de_validacao(exc: RequestValidationError) -> str:
    """Junta os erros num texto só, dizendo o campo de cada um.

    Ex.: "endereco.cep: CEP deve ter 8 dígitos; nome: String should have at
    least 2 characters".
    """
    partes = []
    for erro in exc.errors():
        # O primeiro item do caminho é onde veio o dado (body, query, path).
        campo = ".".join(str(parte) for parte in erro["loc"][1:])
        mensagem = erro["msg"].removeprefix("Value error, ")
        partes.append(f"{campo}: {mensagem}" if campo else mensagem)
    return "; ".join(partes) or "Dados inválidos na requisição"


def registrar_tratamento_de_erros(app: FastAPI) -> None:
    @app.exception_handler(ErroDeNegocio)
    async def erro_de_negocio(request: Request, exc: ErroDeNegocio):
        return resposta_de_erro(exc.status_code, exc.mensagem)

    @app.exception_handler(RequestValidationError)
    async def erro_de_validacao(request: Request, exc: RequestValidationError):
        return resposta_de_erro(422, _descrever_erros_de_validacao(exc))

    @app.exception_handler(StarletteHTTPException)
    async def erro_http(request: Request, exc: StarletteHTTPException):
        # Rota que não existe (404), método errado (405) etc.
        return resposta_de_erro(exc.status_code, str(exc.detail), exc.headers)

    @app.exception_handler(Exception)
    async def erro_inesperado(request: Request, exc: Exception):
        logger.exception("Erro inesperado em %s %s", request.method, request.url.path)
        return resposta_de_erro(500, "Erro interno no servidor")
