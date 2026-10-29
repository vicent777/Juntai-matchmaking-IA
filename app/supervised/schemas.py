"""Projeções explícitas dos perfis TypeORM e contratos históricos v1."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue, StrictBool, model_validator

from app.schemas import Contrato, InvestidorEntrada, StartupEntrada, Segmento, Regiao

Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)]
Count = Annotated[int, Field(ge=0, le=32767, strict=True)]
Identifier = Annotated[str, Field(min_length=1, pattern=r"\S")]
EventType = Literal[
    "visualizacao", "interesse_demonstrado", "conexao_aceita", "reuniao_agendada",
    "reuniao_realizada", "proposta_enviada", "investimento_realizado", "recusado",
]


class InvestorProfile(InvestidorEntrada):
    perfilRisco: Literal["conservador", "moderado", "arrojado"] | None = None
    ticketMinimo: Money | None = None
    ticketMaximo: Money | None = None
    jaAtuouComStartups: StrictBool | None = None
    numeroAproximadoInvestimentos: Count | None = None
    anosExperiencia: Count | None = None
    setoresAtuacao: list[Segmento] = Field(default_factory=list)
    disponibilidade: Literal["algumas_horas_mes", "algumas_horas_semana", "meio_periodo", "dedicacao_integral"] | None = None
    estado: Annotated[str, Field(pattern=r"^[A-Z]{2}$")] | None = None
    cidade: Annotated[str, Field(min_length=1, max_length=100)] | None = None

    @model_validator(mode="after")
    def ticket_interval(self):
        if self.ticketMinimo is not None and self.ticketMaximo is not None:
            if self.ticketMinimo > self.ticketMaximo:
                raise ValueError("ticketMinimo deve ser menor ou igual a ticketMaximo")
        return self


class StartupProfile(StartupEntrada):
    capitalProcurado: Money | None = None
    faturamentoMensal: Money | None = None
    numeroClientes: Annotated[int, Field(ge=0, le=2147483647, strict=True)] | None = None
    tamanhoEquipe: Count | None = None
    taxaCrescimentoPct: Annotated[Decimal, Field(max_digits=6, decimal_places=2, allow_inf_nan=False)] | None = None
    metricaCrescimento: Literal["receita", "clientes", "clientes_e_receita"] | None = None
    periodoComparacaoCrescimento: Literal["ultimos_3_meses", "ultimos_6_meses", "ultimo_ano", "desde_fundacao"] | None = None
    buscaInvestimento: StrictBool | None = None
    regioesCrescimento: list[Regiao] = Field(default_factory=list)
    estado: Annotated[str, Field(pattern=r"^[A-Z]{2}$")] | None = None
    cidade: Annotated[str, Field(min_length=1, max_length=100)] | None = None


class Exposure(Contrato):
    exposicao_id: Identifier
    investidor_id: UUID
    startup_id: UUID
    ocorrido_em: AwareDatetime
    posicao_ranking: Annotated[int, Field(ge=1, strict=True)] | None = None
    origem_recomendacao: Identifier | None = None
    versao_recomendador: Identifier | None = None


class Interaction(Contrato):
    # Projeção SQL: id, investidor_id, startup_id, tipo_evento, ocorrido_em, metadados.
    id: Identifier
    investidor_id: UUID
    startup_id: UUID
    tipo_evento: EventType
    ocorrido_em: AwareDatetime
    metadados: dict[str, JsonValue] | None = None


class ProfileSnapshot(Contrato):
    exposicao_id: Identifier
    estado_em: AwareDatetime
    historico_confirmado: StrictBool
    investidor: InvestorProfile
    startup: StartupProfile


class DatasetInput(Contrato):
    exposicoes: list[Exposure] = Field(default_factory=list)
    interacoes: list[Interaction] = Field(default_factory=list)
    snapshots: list[ProfileSnapshot] = Field(default_factory=list)
    data_corte: AwareDatetime
    janela_dias: Annotated[int, Field(ge=1, le=3650, strict=True)] = 30
    # Declaração da fonte: histórico de todos os pares desde o início, não só da janela.
    historico_completo: StrictBool = False
    completo_ate: AwareDatetime | None = None
    origem_dados: Literal["real", "sintetica"]
    moeda: Literal["BRL"] = "BRL"

    @model_validator(mode="after")
    def completeness(self):
        if self.historico_completo and (self.completo_ate is None or self.completo_ate < self.data_corte):
            raise ValueError("Histórico completo exige completo_ate >= data_corte")
        if not self.historico_completo and self.completo_ate is not None:
            raise ValueError("completo_ate exige declaração historico_completo")
        return self


class QualityIssue(Contrato):
    codigo: str
    referencia: str


class FeatureSet(Contrato):
    numericas: dict[str, float | None]
    categoricas: dict[str, str | bool | None]
    multivaloradas: dict[str, list[str]]
    derivadas: dict[str, float | bool | str | None]
    ausentes: dict[str, bool]


class Label(Contrato):
    target: Literal[0, 1] | None
    status_rotulo: Literal["positivo", "negativo", "censurado", "historico_incompleto", "interesse_previo"]
    evento_interesse_id: str | None = None


class DatasetRow(Contrato):
    metadados: dict[str, JsonValue]
    features: FeatureSet
    rotulo: Label
    auditoria: dict[str, JsonValue]


class DatasetResult(Contrato):
    registros: list[DatasetRow]
    qualidade: list[QualityIssue]
