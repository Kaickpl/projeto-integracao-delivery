"""Coordena cadastro recuperável sem manter senha na base de Perfis."""
import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.exceptions import AcaoNaoPermitida, DadoDuplicado
from src.core.identidade import criar_credencial_e_associar_papel
from src.modules.perfil_usuario.perfil import Perfil


def _resumo_dados_cadastro(dados: dict) -> str:
    serializados = json.dumps(dados, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serializados.encode("utf-8")).hexdigest()


def provisionar_cadastro(
    db: Session,
    perfil: Perfil,
    *,
    senha: str,
    role: str,
    chave_idempotencia: UUID,
    dados_cadastro: dict,
) -> Perfil:
    """Grava o perfil primeiro e permite retomar o Auth/RBAC com a mesma chave.

    Apenas os dados cadastrais não secretos têm fingerprint persistido. A senha
    nunca é guardada em Perfis; o Auth torna a criação repetível verificando a
    credencial existente e o RBAC aplica a associação por upsert.
    """
    fingerprint = _resumo_dados_cadastro(dados_cadastro)
    existente = db.scalar(
        select(Perfil).where(Perfil.chave_idempotencia == chave_idempotencia)
    )
    if existente is not None:
        if existente.tipo != perfil.tipo or existente.dados_cadastro_hash != fingerprint:
            raise AcaoNaoPermitida(
                "Chave de idempotência já utilizada com outros dados de cadastro"
            )
        perfil = existente
    else:
        perfil.identidade_pronta = False
        perfil.chave_idempotencia = chave_idempotencia
        perfil.dados_cadastro_hash = fingerprint
        db.add(perfil)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existente = db.scalar(
                select(Perfil).where(Perfil.chave_idempotencia == chave_idempotencia)
            )
            if existente is None:
                raise DadoDuplicado() from None
            if existente.tipo != perfil.tipo or existente.dados_cadastro_hash != fingerprint:
                raise AcaoNaoPermitida(
                    "Chave de idempotência já utilizada com outros dados de cadastro"
                ) from None
            perfil = existente
        db.refresh(perfil)

    criar_credencial_e_associar_papel(
        perfil.id, perfil.email, senha, role
    )
    perfil.identidade_pronta = True
    db.commit()
    db.refresh(perfil)
    return perfil
