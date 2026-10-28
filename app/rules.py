"""Regras puras: sem HTTP, persistência, autenticação ou acesso ao banco."""

from math import fsum
from types import MappingProxyType
from typing import Mapping
from app.eligibility import evaluate_eligibility

from app.schemas import (
    Criterio, InvestidorEntrada, StartupEntrada, ResultadoCriterio,
    Justificativa, Recomendacao, RulesRequest, RulesResponse, CandidataExcluida,
)

VERSION = "1a-v3"
WEIGHTS = MappingProxyType({"segmento": 30.0, "estagio": 25.0, "regiao": 20.0, "modelo": 15.0, "ajuda": 10.0})
# Equivalências de negócio explícitas, não igualdade entre enums.
# Parcerias estratégicas e "outro" não têm equivalência inequívoca.
HELP_MAP = MappingProxyType({
    "mentoria": "mentoria",
    "conexoes_mercado": "networking",
    "contratacao_talentos": "rh_pessoas",
})


def insufficient(message: str) -> ResultadoCriterio:
    return ResultadoCriterio(estado="insuficiente", score=None, cobertura=0, aviso=message)


def overlap(preferences, values) -> ResultadoCriterio:
    preferences, values = set(preferences), set(values)
    if not preferences or not values:
        return insufficient("Preferências ou características não informadas.")
    common = sorted(preferences & values)
    return ResultadoCriterio(
        estado="compativel" if common else "incompativel",
        score=1.0 if common else 0.0,
        cobertura=1,
        evidencias=common,
    )


def segmento(i: InvestidorEntrada, s: StartupEntrada) -> ResultadoCriterio:
    values = set(s.segmentosSecundarios)
    if s.segmento:
        values.add(s.segmento)
    result = overlap(i.segmentosInteresse, values)
    # Uma correspondência secundária é evidência suficiente. Sem principal,
    # uma ausência de interseção não comprova incompatibilidade setorial.
    if result.score == 0 and s.segmento is None:
        return insufficient("Segmento principal ausente; secundários sem correspondência.")
    return result


def estagio(i: InvestidorEntrada, s: StartupEntrada) -> ResultadoCriterio:
    return overlap(i.estagiosInteresse, [s.estagio] if s.estagio else [])


def regiao(i: InvestidorEntrada, s: StartupEntrada) -> ResultadoCriterio:
    return overlap(i.regioesInteresse, s.regioesAtuacao)


def modelo(i: InvestidorEntrada, s: StartupEntrada) -> ResultadoCriterio:
    return overlap(i.modelosInteresse, [s.modeloNegocio] if s.modeloNegocio else [])


def ajuda(i: InvestidorEntrada, s: StartupEntrada) -> ResultadoCriterio:
    if i.tipoInvestidor == "anjo":
        return insufficient("Modalidade anjo não comprova oferta ativa de mentoria ou apoio; ajuda não avaliada.")
    needs, areas = set(s.necessidadesAdicionais), set(i.areasAjuda)
    unmapped = sorted(needs - HELP_MAP.keys())
    warning = "Necessidades sem equivalência definida: " + ", ".join(unmapped) + "." if unmapped else None
    if not needs or not areas:
        return insufficient("Áreas de ajuda ou necessidades não informadas." + (" " + warning if warning else ""))
    known = needs & HELP_MAP.keys()
    if not known:
        return insufficient(warning)
    matched = sorted(need for need in known if HELP_MAP[need] in areas)
    score = len(matched) / len(known)
    return ResultadoCriterio(
        estado="compativel" if score == 1 else "parcial" if score > 0 else "incompativel",
        score=score,
        cobertura=len(known) / len(needs),
        avaliacaoParcial=bool(unmapped),
        aviso=("Avaliação parcial de ajuda. " + warning) if warning else None,
        evidencias=[f"{need} <- {HELP_MAP[need]}" for need in matched],
    )


CRITERIA = MappingProxyType({"segmento": segmento, "estagio": estagio, "regiao": regiao, "modelo": modelo, "ajuda": ajuda})
EXPLANATIONS = {
    "segmento": "Segmentos da startup alinhados aos interesses do investidor.",
    "estagio": "Estágio da startup contemplado nas preferências.",
    "regiao": "Há região de atuação contemplada nas preferências.",
    "modelo": "Modelo de negócio contemplado nas preferências.",
    "ajuda": "Há necessidades atendidas pelas áreas de ajuda declaradas.",
}


def rank(request: RulesRequest, weights: Mapping[Criterio, float] = WEIGHTS) -> RulesResponse:
    # Configuração apenas no servidor, nunca controlada pelo consumidor HTTP.
    if set(weights) != set(CRITERIA):
        raise ValueError("Configure exatamente os cinco critérios.")
    from math import isfinite
    if any(isinstance(w, bool) or not isfinite(w) or w <= 0 for w in weights.values()):
        raise ValueError("Pesos devem ser finitos e positivos.")
    # Reescala para evitar overflow mesmo com pesos finitos muito grandes.
    maximum = max(weights.values())
    normalized = {key: value / maximum for key, value in weights.items()}
    total = fsum(normalized.values())
    recommendations = []
    excluded = []
    for startup in request.startups:
        eligibility = evaluate_eligibility(request.investidor, startup)
        if eligibility.estado == "inelegivel":
            excluded.append(CandidataExcluida(startupId=startup.id, elegibilidade=eligibility))
            continue
        criteria = {key: calculate(request.investidor, startup) for key, calculate in CRITERIA.items()}
        available = {key: value for key, value in criteria.items() if value.score is not None}
        denominator = fsum(normalized[key] for key in available)
        score = fsum(normalized[key] * value.score for key, value in available.items()) / denominator if denominator else None
        # Afinidade mantém a normalização pelos critérios com score disponível.
        # A fração avaliável afeta cobertura e ranking, sem alterar seus pesos.
        coverage = fsum(normalized[key] * value.cobertura for key, value in criteria.items()) / total
        coverage = min(1.0, max(0.0, coverage))
        score = min(1.0, max(0.0, score)) if score is not None else None
        ranking_score = score * (0.5 + 0.5 * coverage) if score is not None else None
        warnings = [f"{key}: {value.aviso}" for key, value in criteria.items() if value.aviso]
        if any(value.cobertura < 1 for value in criteria.values()):
            warnings.append("Cobertura incompleta; compare o score junto da cobertura.")
        recommendations.append(Recomendacao(
            startupId=startup.id, posicao=1,
            score=score, scoreRanking=ranking_score,
            criterios=criteria, cobertura=coverage,
            criteriosAvaliados=len(available),
            justificativas=[Justificativa(criterio=key, descricao=EXPLANATIONS[key], evidencias=value.evidencias)
                            for key, value in available.items() if value.score > 0],
            avisos=warnings,
            elegibilidade=eligibility,
        ))
    recommendations.sort(key=lambda r: (r.scoreRanking is None, -(r.scoreRanking or 0), -r.cobertura, str(r.startupId)))
    selected = recommendations[:request.limite]
    for position, recommendation in enumerate(selected, start=1):
        recommendation.posicao = position
    return RulesResponse(investidorId=request.investidor.id, versaoAlgoritmo=VERSION,
                         pesos=dict(weights), recomendacoes=selected,
                         tipoInvestidor=request.investidor.tipoInvestidor,
                         excluidas=sorted(excluded, key=lambda item: str(item.startupId)))
