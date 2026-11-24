from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.security import gerar_hash_senha
from src.modules.clientes_servico.models import ClienteServico


class RepositorioClientesServico:
    def __init__(self, sessao: Session) -> None:
        self.sessao = sessao

    def buscar(self, client_id: str) -> ClienteServico | None:
        return self.sessao.get(ClienteServico, client_id)

    def buscar_para_autenticacao(self, client_id: str) -> ClienteServico | None:
        return self.sessao.scalar(
            select(ClienteServico)
            .where(ClienteServico.client_id == client_id)
            .with_for_update()
        )

    def buscar_para_gestao(self, client_id: str) -> ClienteServico | None:
        return self.buscar_para_autenticacao(client_id)

    def criar(self, client_id: str, segredo: str) -> ClienteServico:
        cliente = ClienteServico(
            client_id=client_id,
            segredo_hash=gerar_hash_senha(segredo),
        )
        self.sessao.add(cliente)
        self.sessao.flush()
        return cliente

    def trocar_segredo(self, cliente: ClienteServico, segredo: str) -> None:
        cliente.segredo_hash = gerar_hash_senha(segredo)
        cliente.segredo_atualizado_em = datetime.now(timezone.utc)

    def desativar(self, cliente: ClienteServico) -> None:
        cliente.ativo = False

    def listar_ativos(self):
        return self.sessao.scalars(
            select(ClienteServico).where(ClienteServico.ativo.is_(True))
        )
