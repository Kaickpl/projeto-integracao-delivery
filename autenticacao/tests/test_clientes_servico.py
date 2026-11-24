from src.core.security import verificar_senha
from src.modules.clientes_servico.repository import RepositorioClientesServico


class BancoFalso:
    def __init__(self, cliente=None):
        self.cliente = cliente
        self.adicionados = []

    def get(self, _modelo, _client_id):
        return self.cliente

    def scalar(self, _consulta):
        return self.cliente

    def add(self, valor):
        self.adicionados.append(valor)

    def flush(self):
        pass


def test_criar_cliente_persiste_hash_e_nao_segredo_em_texto():
    db = BancoFalso()
    segredo = "segredo-sintetico-de-servico"

    cliente = RepositorioClientesServico(db).criar("worker-teste", segredo)

    assert db.adicionados == [cliente]
    assert cliente.segredo_hash != segredo
    assert verificar_senha(segredo, cliente.segredo_hash)
    assert not verificar_senha("outro-segredo", cliente.segredo_hash)


def test_rotacao_substitui_hash_e_desativacao_bloqueia_cliente():
    from datetime import datetime, timezone

    from src.modules.clientes_servico.models import ClienteServico

    cliente = ClienteServico(
        client_id="worker-teste",
        segredo_hash="hash-antigo",
        ativo=True,
    )
    repositorio = RepositorioClientesServico(BancoFalso())
    antes = datetime.now(timezone.utc)

    repositorio.trocar_segredo(cliente, "segredo-novo")
    repositorio.desativar(cliente)

    assert cliente.segredo_hash != "segredo-novo"
    assert verificar_senha("segredo-novo", cliente.segredo_hash)
    assert not verificar_senha("segredo-antigo", cliente.segredo_hash)
    assert cliente.segredo_atualizado_em >= antes
    assert cliente.ativo is False


def test_buscar_cliente_de_servico():
    from types import SimpleNamespace

    cliente = SimpleNamespace(client_id="worker-teste")
    repositorio = RepositorioClientesServico(BancoFalso(cliente))

    assert repositorio.buscar("worker-teste") is cliente
    assert repositorio.buscar_para_autenticacao("worker-teste") is cliente
