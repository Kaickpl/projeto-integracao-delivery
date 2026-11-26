from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.permissoes import protegida
from src.modules.loja import service
from src.modules.loja.schemas import (
    Horario,
    HorariosUpdate,
    LojaCreate,
    LojaInformacoesUpdate,
    LojaPerfilUpdate,
    LojaPublicaResponse,
    LojaResponse,
    StatusFuncionamentoUpdate,
)
from src.modules.perfil_usuario.loja import CategoriaLoja, StatusFuncionamento

router = APIRouter(prefix="/lojas", tags=["lojas"])

# Editar e remover: a própria loja ou um ADMIN.
EDITAR = protegida(
    qualquer="perfis:editar_qualquer", proprio="perfil:editar_proprio", dono="loja_id"
)
REMOVER = protegida(
    qualquer="perfis:remover_qualquer", proprio="perfil:remover_proprio", dono="loja_id"
)


@router.post("", response_model=LojaResponse, status_code=201)
def cadastrar_loja(
    dados: LojaCreate,
    chave_idempotencia: UUID = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    return service.cadastrar_loja(db, dados, chave_idempotencia)


@router.get("", response_model=list[LojaPublicaResponse])
def buscar_lojas(
    nome: str | None = Query(
        None, min_length=1, max_length=150, description="Parte do nome da loja"
    ),
    categoria: CategoriaLoja | None = None,
    status_funcionamento: StatusFuncionamento | None = None,
    cidade: str | None = Query(None, min_length=1, max_length=100),
    bairro: str | None = Query(None, min_length=1, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Busca de lojas para o cliente. Os filtros podem ser combinados.

    Só aparecem lojas com a conta ativa (aprovadas pelo admin). As abertas
    vêm primeiro. Rota pública: não devolve CNPJ, e-mail nem telefone.
    """
    return service.buscar_lojas(
        db, nome, categoria, status_funcionamento, cidade, bairro, skip, limit
    )


@router.get("/{loja_id}", response_model=LojaPublicaResponse)
def buscar_loja(loja_id: UUID, db: Session = Depends(get_db)):
    """Rota pública: não devolve CNPJ, e-mail nem telefone."""
    return service.buscar_loja(db, loja_id)


@router.get(
    "/{loja_id}/perfil",
    response_model=LojaResponse,
    **protegida(
        qualquer="perfis:listar", proprio="perfil:ler_proprio", dono="loja_id"
    ),
)
def buscar_perfil_completo(loja_id: UUID, db: Session = Depends(get_db)):
    """Todos os dados da loja, inclusive os de contato. Só a própria loja ou um ADMIN."""
    return service.buscar_loja(db, loja_id)


@router.patch("/{loja_id}", response_model=LojaResponse, **EDITAR)
def editar_perfil(loja_id: UUID, dados: LojaPerfilUpdate, db: Session = Depends(get_db)):
    """Dados da conta: nome, e-mail, telefone e razão social."""
    return service.atualizar_perfil(db, loja_id, dados)


@router.patch("/{loja_id}/informacoes", response_model=LojaResponse, **EDITAR)
def editar_informacoes(
    loja_id: UUID, dados: LojaInformacoesUpdate, db: Session = Depends(get_db)
):
    """O que o cliente vê: descrição, imagem, categoria, taxa, tempo e endereço."""
    return service.atualizar_informacoes(db, loja_id, dados)


@router.get("/{loja_id}/horarios", response_model=list[Horario])
def listar_horarios(loja_id: UUID, db: Session = Depends(get_db)):
    """Horários de funcionamento, por dia da semana."""
    return service.listar_horarios(db, loja_id)


@router.put("/{loja_id}/horarios", response_model=list[Horario], **EDITAR)
def definir_horarios(
    loja_id: UUID, dados: HorariosUpdate, db: Session = Depends(get_db)
):

    return service.definir_horarios(db, loja_id, dados)


@router.patch(
    "/{loja_id}/status",
    response_model=LojaResponse,
    **protegida(proprio="loja:operar", dono="loja_id"),
)
def alterar_status_funcionamento(
    loja_id: UUID, dados: StatusFuncionamentoUpdate, db: Session = Depends(get_db)
):
    """Abrir ou fechar a loja. Só a própria loja."""
    return service.alterar_status_funcionamento(db, loja_id, dados.status_funcionamento)


@router.delete("/{loja_id}", status_code=204, **REMOVER)
def apagar_loja(loja_id: UUID, db: Session = Depends(get_db)):
    service.remover_loja(db, loja_id)
