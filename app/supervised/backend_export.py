"""Adapta uma projeção exportada pelo Node; nunca consulta PostgreSQL."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime

from app.schemas import Contrato
from app.supervised.schemas import Exposure, InvestorProfile, ProfileSnapshot, StartupProfile


class StoredProfiles(Contrato):
    investidor: InvestorProfile
    startup: StartupProfile


class StoredExposure(Contrato):
    id: UUID
    investidor_id: UUID
    startup_id: UUID
    ocorrido_em: AwareDatetime
    origem_recomendacao: Literal["discovery", "rules"]
    posicao_ranking: int | None
    versao_recomendador: str | None
    snapshot_perfis: StoredProfiles
    versao_contrato: Literal["supervised-v1"]
    semantica: Literal["card_50pct_1000ms_ack"]
    origem_dados: Literal["real", "sintetica"]


def adapt_exposure(row: dict) -> tuple[Exposure, ProfileSnapshot]:
    stored = StoredExposure.model_validate(row)
    if (stored.investidor_id, stored.startup_id) != (stored.snapshot_perfis.investidor.id, stored.snapshot_perfis.startup.id):
        raise ValueError("Par inconsistente na exposição exportada")
    exposure = Exposure(
        exposicao_id=str(stored.id), investidor_id=stored.investidor_id,
        startup_id=stored.startup_id, ocorrido_em=stored.ocorrido_em,
        origem_recomendacao=stored.origem_recomendacao,
        posicao_ranking=stored.posicao_ranking, versao_recomendador=stored.versao_recomendador,
    )
    snapshot = ProfileSnapshot(
        exposicao_id=str(stored.id), estado_em=stored.ocorrido_em,
        historico_confirmado=True, investidor=stored.snapshot_perfis.investidor,
        startup=stored.snapshot_perfis.startup,
    )
    return exposure, snapshot
