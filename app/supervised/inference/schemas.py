"""Perfis de entrada reutilizam os contratos supervisionados existentes."""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas import Contrato, CandidataExcluida, Unitario
from app.supervised.schemas import InvestorProfile, StartupProfile


class SupervisedRequest(Contrato):
    investidor: InvestorProfile
    startups: list[StartupProfile] = Field(min_length=1, max_length=10000)
    limite: int = Field(default=24, ge=1, le=1000, strict=True)

    @model_validator(mode='after')
    def unique_startups(self):
        if len({s.id for s in self.startups}) != len(self.startups):
            raise ValueError('IDs de startups duplicados.')
        return self


class ModelIdentity(Contrato):
    modelo: str
    versaoModelo: str
    versaoContrato: Literal['supervised-v1']
    versaoFeatures: Literal['profiles-rules-v1']
    versaoTarget: Literal['first-interest-v1']


class SupervisedRecommendation(ModelIdentity):
    startupId: UUID
    posicao: int = Field(ge=1)
    probabilidadeInteresse: Unitario
    avisos: list[str]


class SupervisedResponse(ModelIdentity):
    investidorId: UUID
    experimental: Literal[True] = True
    origemTreinamento: Literal['sintetica'] = 'sintetica'
    janelaInteresseDias: Literal[30] = 30
    recomendacoes: list[SupervisedRecommendation]
    excluidas: list[CandidataExcluida]
    avisos: list[str]
