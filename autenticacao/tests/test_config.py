import pytest
from pydantic import ValidationError

from src.core.config import Settings


def test_rejeita_url_com_driver_incorreto_sem_expor_a_senha():
    segredo = "segredo-sintetico"
    with pytest.raises(ValidationError, match=r"deve usar postgresql\+psycopg") as erro:
        Settings(DATABASE_URL=f"postgresql://usuario:{segredo}@127.0.0.1/banco")

    assert segredo not in str(erro.value)


def test_rejeita_url_malformada_sem_expor_o_valor():
    with pytest.raises(ValidationError, match="DATABASE_URL inválida") as erro:
        Settings(DATABASE_URL="valor-confidencial-sintetico")

    assert "valor-confidencial-sintetico" not in str(erro.value)
