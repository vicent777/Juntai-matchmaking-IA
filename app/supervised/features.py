"""Representação intermediária sem imputação, encoders ajustados ou labels."""

from app.rules import CRITERIA
from app.supervised.schemas import FeatureSet, InvestorProfile, StartupProfile

INV_NUM = ("ticketMinimo", "ticketMaximo", "anosExperiencia", "numeroAproximadoInvestimentos")
STA_NUM = ("capitalProcurado", "faturamentoMensal", "numeroClientes", "tamanhoEquipe", "taxaCrescimentoPct")
INV_CAT = ("tipoInvestidor", "perfilRisco", "disponibilidade", "estado", "cidade", "jaAtuouComStartups")
STA_CAT = ("segmento", "estagio", "modeloNegocio", "estado", "cidade", "metricaCrescimento", "periodoComparacaoCrescimento", "buscaInvestimento")
INV_MULTI = ("segmentosInteresse", "estagiosInteresse", "regioesInteresse", "modelosInteresse", "areasAjuda", "setoresAtuacao")
STA_MULTI = ("segmentosSecundarios", "regioesAtuacao", "regioesCrescimento", "necessidadesAdicionais")


def build_features(investor: InvestorProfile, startup: StartupProfile) -> FeatureSet:
    numeric, categorical, multi = {}, {}, {}
    for prefix, profile, nums, cats, arrays in (
        ("investidor", investor, INV_NUM, INV_CAT, INV_MULTI),
        ("startup", startup, STA_NUM, STA_CAT, STA_MULTI),
    ):
        numeric.update({f"{prefix}.{key}": float(getattr(profile, key)) if getattr(profile, key) is not None else None for key in nums})
        categorical.update({f"{prefix}.{key}": getattr(profile, key) for key in cats})
        multi.update({f"{prefix}.{key}": sorted(set(getattr(profile, key))) for key in arrays})
    derived = {}
    for name, calculate in CRITERIA.items():
        result = calculate(investor, startup)
        derived.update({f"{name}.score": result.score, f"{name}.cobertura": result.cobertura,
                        f"{name}.parcial": result.avaliacaoParcial, f"{name}.estado": result.estado})
    for name, left, right in (
        ("segmentos", investor.segmentosInteresse, startup.segmentosSecundarios + ([startup.segmento] if startup.segmento else [])),
        ("regioes", investor.regioesInteresse, startup.regioesAtuacao),
        ("experiencia_setor", investor.setoresAtuacao, [startup.segmento] if startup.segmento else []),
    ):
        derived[f"{name}.correspondencias"] = len(set(left) & set(right)) if left and right else None
    # Razão descritiva, nunca um veto: capital total não equivale a um cheque.
    derived["capital_por_ticket_maximo"] = (
        float(startup.capitalProcurado / investor.ticketMaximo)
        if startup.capitalProcurado is not None and investor.ticketMaximo else None
    )
    missing = {key: value is None for key, value in {**numeric, **categorical, **derived}.items()}
    missing.update({key: not value for key, value in multi.items()})
    return FeatureSet(numericas=numeric, categoricas=categorical, multivaloradas=multi, derivadas=derived, ausentes=missing)
