"""Adapta uma projeção exportada pelo Node; nunca consulta PostgreSQL."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

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
    origem_recomendacao: Literal["discovery", "rules", "supervised"]
    posicao_ranking: Annotated[int, Field(ge=1, strict=True)] | None
    versao_recomendador: Annotated[str, Field(min_length=1, max_length=100)] | None
    snapshot_perfis: StoredProfiles
    versao_contrato: Literal["supervised-v1"]
    semantica: Literal["card_50pct_1000ms_ack"]
    origem_dados: Literal["real", "sintetica"]

    @model_validator(mode="after")
    def supervised_provenance(self):
        # Contextos supervisionados emitidos pelo backend sempre têm posição/versão.
        # Não inventar esses metadados para registros incompletos ou legados.
        if self.origem_recomendacao == "supervised" and (
            self.posicao_ranking is None or not self.versao_recomendador or not self.versao_recomendador.strip()
        ):
            raise ValueError("Exposição supervised exige posição e versão do recomendador")
        return self


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
