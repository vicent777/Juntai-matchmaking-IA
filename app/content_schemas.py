"""Contratos independentes do Nível 1A, projetados das entidades TypeORM."""
from typing import Annotated, Any
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas import Contrato, Unitario

Texto = Annotated[str, Field(max_length=20000)]


class InvestidorConteudo(Contrato):
    id: UUID
    bio: Texto | None = None
    descricaoExperiencia: Texto | None = None


class StartupConteudo(Contrato):
    id: UUID
    descricaoCurta: Annotated[str, Field(max_length=300)] | None = None
    descricaoPitch: Texto | None = None
    mercadoAlvo: Annotated[str, Field(max_length=200)] | None = None
    canvasJson: dict[str, Any] | None = None


class ContentRequest(Contrato):
    investidor: InvestidorConteudo
    startups: list[StartupConteudo] = Field(max_length=1000)
    limite: int = Field(default=10, ge=1, le=1000, strict=True)

    @model_validator(mode="after")
    def ids_unicos(self):
        ids = [s.id for s in self.startups]
        if len(ids) != len(set(ids)):
            raise ValueError("IDs de startups duplicados.")
        return self


class ContentRecommendation(Contrato):
    startupId: UUID
    posicao: int = Field(ge=1)
    similaridadeBruta: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)] | None
    score: Unitario | None
    avisos: list[str]


class ContentResponse(Contrato):
    investidorId: UUID
    versaoAlgoritmo: str
    modeloEmbeddings: str
    recomendacoes: list[ContentRecommendation]
    avisos: list[str]
