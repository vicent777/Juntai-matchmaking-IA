"""Orquestração determinística, uma linha por par, com relatório de qualidade."""

from collections import defaultdict
from datetime import timedelta, timezone

from app.supervised.features import build_features
from app.supervised.schemas import DatasetInput, DatasetResult, DatasetRow, QualityIssue
from app.supervised.targets import build_target
from app.supervised.validation import unique_by_id

CONTRACT_VERSION = "supervised-v1"
FEATURE_VERSION = "profiles-rules-v1"
TARGET_VERSION = "first-interest-v1"


def build_dataset(data: DatasetInput) -> DatasetResult:
    # Revalidar inclusive modelos alterados depois da construção.
    data = DatasetInput.model_validate(data.model_dump())
    issues, rows = [], []

    def report(code, ref):
        issues.append(QualityIssue(codigo=code, referencia=str(ref)))

    exposures = unique_by_id(data.exposicoes, "exposicao_id", issues)
    events = unique_by_id(data.interacoes, "id", issues)
    snapshots = {s.exposicao_id: s for s in unique_by_id(data.snapshots, "exposicao_id", issues)}
    exposure_map = {e.exposicao_id: e for e in exposures}
    for key, snapshot in snapshots.items():
        exposure = exposure_map.get(key)
        if exposure is None:
            raise ValueError(f"Snapshot sem exposição: {key}")
        if (snapshot.investidor.id, snapshot.startup.id) != (exposure.investidor_id, exposure.startup_id):
            raise ValueError(f"Par inconsistente no snapshot: {key}")
    grouped, event_pairs = defaultdict(list), defaultdict(list)
    for exposure in exposures:
        if exposure.ocorrido_em > data.data_corte:
            report("exposicao_futura", exposure.exposicao_id)
        else:
            grouped[(exposure.investidor_id, exposure.startup_id)].append(exposure)
    for event in events:
        if event.ocorrido_em > data.data_corte:
            report("evento_futuro", event.id)
        else:
            event_pairs[(event.investidor_id, event.startup_id)].append(event)
    for pair in sorted(event_pairs, key=str):
        if pair not in grouped:
            report("interacao_sem_exposicao", event_pairs[pair][0].id)
    if not data.historico_completo:
        report("historico_incompleto", "lote")
    for pair, candidates in sorted(grouped.items(), key=lambda item: str(item[0])):
        candidates.sort(key=lambda e: (e.ocorrido_em, e.exposicao_id))
        # Nunca substituir a primeira exposição por outra com snapshot mais conveniente.
        exposure = candidates[0]
        if len(candidates) > 1:
            report("multiplas_exposicoes", exposure.exposicao_id)
        snapshot = snapshots.get(exposure.exposicao_id)
        if snapshot is None:
            report("snapshot_ausente", exposure.exposicao_id)
            continue
        if not snapshot.historico_confirmado or snapshot.estado_em != exposure.ocorrido_em:
            report("snapshot_invalido", exposure.exposicao_id)
            continue
        pair_events = sorted(event_pairs[pair], key=lambda e: (e.ocorrido_em, e.id))
        interests = [e for e in pair_events if e.tipo_evento == "interesse_demonstrado"]
        if len(interests) > 1:
            report("multiplos_interesses", exposure.exposicao_id)
        t0 = exposure.ocorrido_em.astimezone(timezone.utc)
        end = t0 + timedelta(days=data.janela_dias)
        label = build_target(t0, end, data.data_corte, pair_events, data.historico_completo)
        if label.target is None:
            report(label.status_rotulo, exposure.exposicao_id)
        rows.append(DatasetRow(
            metadados={"investidor_id": str(pair[0]), "startup_id": str(pair[1]),
                       "exposicao_id": exposure.exposicao_id, "t0": t0.isoformat(),
                       "fim_janela": end.isoformat(), "data_corte": data.data_corte.astimezone(timezone.utc).isoformat(),
                       "versao_contrato": CONTRACT_VERSION, "versao_features": FEATURE_VERSION,
                       "versao_target": TARGET_VERSION, "origem_dados": data.origem_dados, "moeda": data.moeda},
            features=build_features(snapshot.investidor, snapshot.startup), rotulo=label,
            auditoria={"exposicoes_ids": [e.exposicao_id for e in candidates],
                       "eventos_ids": [e.id for e in pair_events],
                       "snapshot_estado_em": snapshot.estado_em.isoformat(),
                       "historico_completo": data.historico_completo,
                       "completo_ate": data.completo_ate.isoformat() if data.completo_ate else None,
                       "posicao_ranking": exposure.posicao_ranking,
                       "origem_recomendacao": exposure.origem_recomendacao,
                       "versao_recomendador": exposure.versao_recomendador},
        ))
    return DatasetResult(registros=rows, qualidade=issues)
