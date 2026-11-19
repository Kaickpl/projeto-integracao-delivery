import enum
import uuid

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .endereco import Endereco
from .perfil import Perfil, TipoPerfil


class CategoriaLoja(str, enum.Enum):
    PIZZARIA = "PIZZARIA"
    HAMBURGUERIA = "HAMBURGUERIA"
    LANCHONETE = "LANCHONETE"
    JAPONESA = "JAPONESA"
    BRASILEIRA = "BRASILEIRA"
    ITALIANA = "ITALIANA"
    ARABE = "ARABE"
    CHINESA = "CHINESA"
    SAUDAVEL = "SAUDAVEL"
    DOCERIA = "DOCERIA"
    ACAITERIA = "ACAITERIA"
    PADARIA = "PADARIA"
    BEBIDAS = "BEBIDAS"
    OUTROS = "OUTROS"


class StatusFuncionamento(str, enum.Enum):
    ABERTO = "ABERTO"
    FECHADO = "FECHADO"
    INDISPONIVEL = "INDISPONIVEL"


class Loja(Perfil):

    __tablename__ = "lojas"

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("perfis.id", ondelete="CASCADE"), primary_key=True
    )
    razao_social: Mapped[str] = mapped_column(String(150))
    descricao: Mapped[str | None] = mapped_column(String(500))
    url_imagem: Mapped[str | None] = mapped_column(String(500))
    categoria: Mapped[CategoriaLoja] = mapped_column(
        Enum(CategoriaLoja, name="categoria_loja")
    )
    # Em centavos (R$ 5,90 -> 590), como no padrão da turma.
    taxa_entrega: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    # Em minutos.
    tempo_estimado_min: Mapped[int | None] = mapped_column(Integer)
    tempo_estimado_max: Mapped[int | None] = mapped_column(Integer)
    # Não é o `status` de Perfil (situação da conta): diz se a loja está
    # recebendo pedidos agora.
    status_funcionamento: Mapped[StatusFuncionamento] = mapped_column(
        Enum(StatusFuncionamento, name="status_funcionamento"),
        default=StatusFuncionamento.FECHADO,
        server_default=StatusFuncionamento.FECHADO.value,
    )

    # Uma loja tem no máximo um endereço (garantido também no banco pelo
    # índice `uq_endereco_unico_por_loja`).
    endereco: Mapped[Endereco | None] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("taxa_entrega >= 0", name="ck_loja_taxa_entrega_nao_negativa"),
        CheckConstraint(
            "tempo_estimado_min > 0 AND tempo_estimado_max > 0",
            name="ck_loja_tempo_estimado_positivo",
        ),
        CheckConstraint(
            "tempo_estimado_max >= tempo_estimado_min",
            name="ck_loja_tempo_estimado_max_maior_que_min",
        ),
    )

    __mapper_args__ = {
        "polymorphic_identity": TipoPerfil.LOJA,
        "polymorphic_load": "selectin",
    }
