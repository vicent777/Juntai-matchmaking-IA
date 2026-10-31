"""Mundo simulado reproduzível: perfis fixos, decisões estocásticas e tempo coerente."""

import math
import random
from bisect import bisect
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import get_args
from uuid import UUID

from app.schemas import Segmento, Estagio, Modelo
from app.supervised.schemas import DatasetInput, Exposure, Interaction, ProfileSnapshot

VERSION = "behavior-synthetic-v1"


@dataclass(frozen=True)
class Config:
    seed: int
    exposures: int
    cutoff: datetime

    def __post_init__(self):
        if isinstance(self.exposures, bool) or not isinstance(self.exposures, int) or self.exposures < 1:
            raise ValueError("exposures deve ser um inteiro positivo")
        if self.cutoff.tzinfo is None or self.cutoff.utcoffset() is None:
            raise ValueError("cutoff exige timezone")


def cumulative(weights):
    result, total = [], 0.0
    for weight in weights:
        total += weight
        result.append(total)
    return result


def draw(rng, weights):
    return bisect(weights, rng.random() * weights[-1])


def behavioral_probability(investor, startup, taste, noise):
    """Não recebe scores/labels. Interações não lineares e gostos latentes próprios."""
    declared = startup.segmento in investor.segmentosInteresse
    stage = startup.estagio in investor.estagiosInteresse
    hidden_sector = startup.segmento == taste["sector"]
    combination = startup.estagio == taste["stage"] and startup.modeloNegocio == taste["model"]
    growth = max(-1.0, min(1.0, float(startup.taxaCrescimentoPct or 0) / 50))
    traction = math.log1p(float(startup.numeroClientes or 0)) / 10
    early = startup.estagio in ("ideacao", "validacao", "mvp")
    risk = (0.7 if early else -0.2) if investor.perfilRisco == "arrojado" else (-0.5 if early else 0.4)
    experience = startup.segmento in investor.setoresAtuacao
    capital_fit = 0.0
    if startup.capitalProcurado and investor.ticketMaximo:
        ratio = float(startup.capitalProcurado / investor.ticketMaximo)
        capital_fit = -0.2 * math.log1p(ratio)
    logit = (-2.6 + taste["bias"] + 0.65 * declared + 0.25 * stage
             + 1.25 * hidden_sector + 1.1 * combination + 0.45 * experience
             + taste["growth"] * growth + 0.35 * traction + risk + capital_fit + noise)
    return 0.02 + 0.90 / (1 + math.exp(-max(-15, min(15, logit))))


def generate(investors, startups, config: Config) -> DatasetInput:
    investors = sorted(investors, key=lambda p: str(p.id))
    startups = sorted(startups, key=lambda p: str(p.id))
    if not investors or not startups:
        raise ValueError("São necessários perfis existentes válidos dos dois tipos")
    if len({p.id for p in investors}) != len(investors) or len({p.id for p in startups}) != len(startups):
        raise ValueError("Perfis com IDs duplicados")
    rng = random.Random(config.seed)
    cutoff = config.cutoff.astimezone(timezone.utc)
    investor_weights = cumulative([rng.lognormvariate(0, 0.8) for _ in investors])
    startup_weights = cumulative([rng.lognormvariate(0, 0.5) for _ in startups])
    tastes = [{"sector": rng.choice(get_args(Segmento)), "stage": rng.choice(get_args(Estagio)),
               "model": rng.choice(get_args(Modelo)), "bias": rng.gauss(0, 0.7),
               "growth": rng.uniform(-0.3, 1.0)} for _ in investors]
    buckets = {}
    for index, startup in enumerate(startups):
        buckets.setdefault(startup.segmento, []).append(index)
    unique_count = min(len(investors) * len(startups), max(1, round(config.exposures * 0.85)))
    coverage = list(range(len(investors)))
    rng.shuffle(coverage)
    pairs, used = [], set()
    for index in range(unique_count):
        i = coverage[index] if index < len(coverage) else draw(rng, investor_weights)
        for attempt in range(100):
            preferred = [s for segment in investors[i].segmentosInteresse for s in buckets.get(segment, [])]
            j = rng.choice(preferred) if preferred and rng.random() < 0.45 else draw(rng, startup_weights)
            if (i, j) not in used:
                break
            if attempt > 20:
                i = draw(rng, investor_weights)
        else:
            i, j = next((a, b) for a in range(len(investors)) for b in range(len(startups)) if (a, b) not in used)
        used.add((i, j))
        pairs.append((i, j))
    exposures, snapshots, events = [], [], []

    def identifier():
        return str(UUID(int=rng.getrandbits(128), version=4))

    def expose(i, j, when):
        exposure = Exposure(exposicao_id=identifier(), investidor_id=investors[i].id,
                            startup_id=startups[j].id, ocorrido_em=when,
                            origem_recomendacao="discovery", versao_recomendador=VERSION)
        exposures.append(exposure)
        # Confirmação somente dentro do mundo simulado, nunca evidência histórica real.
        snapshots.append(ProfileSnapshot(exposicao_id=exposure.exposicao_id, estado_em=when,
                                        historico_confirmado=True, investidor=investors[i], startup=startups[j]))
        if rng.random() < 0.7:
            events.append(Interaction(id=identifier(), investidor_id=investors[i].id,
                                      startup_id=startups[j].id, tipo_evento="visualizacao",
                                      ocorrido_em=when + timedelta(seconds=rng.randint(1, 60)),
                                      metadados={"origem_dados": "sintetica"}))

    first_times = []
    for i, j in pairs:
        age = rng.randint(1, 29) if rng.random() < 0.2 else rng.randint(31, 120)
        t0 = cutoff - timedelta(days=age, seconds=rng.randint(1, 86399))
        first_times.append(t0)
        expose(i, j, t0)
        probability = behavioral_probability(investors[i], startups[j], tastes[i], rng.gauss(0, 0.6))
        if rng.random() < probability:
            delay = rng.uniform(31, 45) if rng.random() < 0.10 else min(30, max(1 / 86400, rng.expovariate(1 / 9)))
            when = t0 + timedelta(days=delay)
            if when <= cutoff:
                events.append(Interaction(id=identifier(), investidor_id=investors[i].id,
                                          startup_id=startups[j].id, tipo_evento="interesse_demonstrado",
                                          ocorrido_em=when, metadados={"origem_dados": "sintetica"}))
    for _ in range(config.exposures - unique_count):
        pair = rng.randrange(len(pairs))
        i, j = pairs[pair]
        # Deixa um minuto para a visualização, sem eventos posteriores ao corte.
        elapsed = (cutoff - first_times[pair]).total_seconds()
        expose(i, j, first_times[pair] + timedelta(seconds=rng.uniform(1, elapsed - 61)))
    exposures.sort(key=lambda e: (e.ocorrido_em, e.exposicao_id))
    snapshots.sort(key=lambda s: s.exposicao_id)
    events.sort(key=lambda e: (e.ocorrido_em, e.id))
    return DatasetInput(exposicoes=exposures, snapshots=snapshots, interacoes=events,
                        data_corte=cutoff, janela_dias=30, historico_completo=True,
                        completo_ate=cutoff, origem_dados="sintetica")
