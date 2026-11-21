from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.security import gerar_hash_senha
from src.modules.credenciais.models import Credencial


class RepositorioCredenciais:
    def __init__(self, sessao: Session) -> None:
        self.sessao = sessao

    def criar(self, conta_id: UUID, email: str, senha: str) -> Credencial:
        credencial = Credencial(
            conta_id=conta_id,
            email=email.strip(),
            senha_hash=gerar_hash_senha(senha),
        )
        self.sessao.add(credencial)
        self.sessao.flush()
        return credencial

    def buscar_por_conta_id(self, conta_id: UUID) -> Credencial | None:
        return self.sessao.get(Credencial, conta_id)

    def buscar_por_email(self, email: str) -> Credencial | None:
        consulta = select(Credencial).where(
            func.lower(Credencial.email) == func.lower(email.strip())
        )
        return self.sessao.scalar(consulta)
