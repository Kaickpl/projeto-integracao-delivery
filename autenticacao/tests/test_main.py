import asyncio

from httpx import ASGITransport, AsyncClient

from src.main import app


def test_rotas_existentes():
    async def consultar_rotas():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://teste") as cliente:
            assert (await cliente.get("/")).json() == {"message": "Hello World"}
            assert (await cliente.get("/hello/Dev")).json() == {"message": "Hello Dev"}
            assert (await cliente.get("/health")).json() == {"status": "ok"}

    asyncio.run(consultar_rotas())
