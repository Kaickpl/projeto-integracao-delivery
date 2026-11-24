from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.exceptions import DadoDuplicado
from src.core.identidade import criar_credencial_e_associar_papel
from src.modules.cliente.schemas import ClienteCreate
from src.modules.perfil_usuario.cliente import Cliente
from src.modules.perfil_usuario.perfil import StatusConta, TipoPerfil


def cadastrar_cliente(db: Session, dados: ClienteCreate) -> Cliente:
    cliente = Cliente(
        tipo=TipoPerfil.CLIENTE,
        nome=dados.nome,
        cpf_cnpj=dados.cpf,
        email=str(dados.email),
        telefone=dados.telefone,
        status=StatusConta.PENDENTE_APROVACAO,
    )
    db.add(cliente)
    db.flush()
    criar_credencial_e_associar_papel(cliente.id, cliente.email, dados.senha, "CLIENTE")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DadoDuplicado() from None
    db.refresh(cliente)
    return cliente
