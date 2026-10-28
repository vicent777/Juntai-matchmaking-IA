"""Contrato mínimo; enums espelham src/shared/enums/index.ts do backend."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

Segmento = Literal["fintech", "healthtech", "edtech", "agtech", "saas_b2b", "marketplace", "ecommerce", "economia_criativa"]
Estagio = Literal["ideacao", "validacao", "mvp", "tracao", "crescimento", "escala"]
Regiao = Literal["norte", "nordeste", "centro_oeste", "sudeste", "sul"]
Modelo = Literal["b2b", "b2c", "b2b2c", "marketplace", "assinatura_saas"]
Area = Literal["mentoria", "networking", "operacoes", "vendas_marketing", "growth", "financeiro_juridico", "produto_tecnologia", "rh_pessoas"]
Necessidade = Literal["mentoria", "conexoes_mercado", "contratacao_talentos", "parcerias_estrategicas", "outro"]
Criterio = Literal["segmento", "estagio", "regiao", "modelo", "ajuda"]
Unitario = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
TipoInvestidor = Literal["anjo", "mentor", "anjo_mentor"]
StatusModeracao = Literal["pendente", "aprovado", "rejeitado", "suspenso"]


class Contrato(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UsuarioOperacional(Contrato):
    """Projeção opcional da relação usuario, sem default de atividade."""
    id: UUID | None = None
    ativo: StrictBool | None = None


class InvestidorEntrada(Contrato):
    id: UUID  # Investidor.id, nunca Usuario.id.
    usuario: UsuarioOperacional | None = None
    tipoInvestidor: TipoInvestidor | None = None
    segmentosInteresse: list[Segmento] = Field(default_factory=list)
    estagiosInteresse: list[Estagio] = Field(default_factory=list)
    regioesInteresse: list[Regiao] = Field(default_factory=list)
    modelosInteresse: list[Modelo] = Field(default_factory=list)
    areasAjuda: list[Area] = Field(default_factory=list)


class StartupEntrada(Contrato):
    id: UUID  # Startup.id, nunca Usuario.id.
    usuario: UsuarioOperacional | None = None
    statusModeracao: StatusModeracao | None = None
    segmento: Segmento | None = None
    segmentosSecundarios: list[Segmento] = Field(default_factory=list)
    estagio: Estagio | None = None
    regioesAtuacao: list[Regiao] = Field(default_factory=list)
    modeloNegocio: Modelo | None = None
    necessidadesAdicionais: list[Necessidade] = Field(default_factory=list)


class RulesRequest(Contrato):
    investidor: InvestidorEntrada
    startups: list[StartupEntrada] = Field(max_length=10000)
    limite: int = Field(default=10, ge=1, le=1000, strict=True)

    @model_validator(mode="after")
    def ids_unicos(self):
        ids = [startup.id for startup in self.startups]
        if len(ids) != len(set(ids)):
            raise ValueError("IDs de startups duplicados.")
        return self


class ResultadoCriterio(Contrato):
    estado: Literal["compativel", "parcial", "incompativel", "insuficiente"]
    score: Unitario | None
    cobertura: Unitario
    avaliacaoParcial: bool = False
    evidencias: list[str] = Field(default_factory=list)
    aviso: str | None = None


class Justificativa(Contrato):
    criterio: Criterio
    descricao: str
    evidencias: list[str]


class ResultadoElegibilidade(Contrato):
    estado: Literal["elegivel", "inelegivel", "indeterminado"]
    verificadas: list[str]
    impedimentos: list[str]
    pendencias: list[str]


class CandidataExcluida(Contrato):
    startupId: UUID
    elegibilidade: ResultadoElegibilidade


class Recomendacao(Contrato):
    startupId: UUID
    posicao: int = Field(ge=1)
    score: Unitario | None
    scoreRanking: Unitario | None
    criterios: dict[Criterio, ResultadoCriterio]
    cobertura: Unitario
    criteriosAvaliados: int = Field(ge=0, le=5)
    justificativas: list[Justificativa]
    avisos: list[str]
    elegibilidade: ResultadoElegibilidade


class RulesResponse(Contrato):
    investidorId: UUID
    versaoAlgoritmo: str
    pesos: dict[Criterio, float]
    recomendacoes: list[Recomendacao]
    tipoInvestidor: TipoInvestidor | None = None
    excluidas: list[CandidataExcluida] = Field(default_factory=list)
