"""Artefatos separados para auditoria e treinamento futuro; sem ajustar modelos."""

import hashlib
import json
from collections import Counter
from pathlib import Path

from app.supervised.dataset import build_dataset
from app.supervised.features import build_features
from app.supervised.schemas import DatasetInput, DatasetRow


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def export_run(output: Path, data: DatasetInput, profiles, quality, config, provenance):
    output.mkdir(parents=True, exist_ok=False)
    source = {"investidores": [p.model_dump(mode="json") for p in profiles[0]],
              "startups": [p.model_dump(mode="json") for p in profiles[1]], "qualidade": quality}
    write_json(output / "profiles.json", source)
    (output / "input.json").write_text(data.model_dump_json() + "\n", encoding="utf-8")
    result = build_dataset(data)
    first_by_id = {s.exposicao_id: s for s in data.snapshots}
    for row in result.registros:
        snapshot = first_by_id[row.metadados["exposicao_id"]]
        if row.features != build_features(snapshot.investidor, snapshot.startup):
            raise ValueError("Features inconsistentes com snapshot da primeira exposição")
    with (output / "dataset.jsonl").open("w", encoding="utf-8", newline="\n") as audit, (output / "training.jsonl").open("w", encoding="utf-8", newline="\n") as training:
        for row in result.registros:
            audit.write(row.model_dump_json() + "\n")
            if row.rotulo.target is not None:
                # IDs, datas, eventos e campos de auditoria não entram na matriz de features.
                training.write(json.dumps({"features": row.features.model_dump(mode="json"), "target": row.rotulo.target}, ensure_ascii=False, sort_keys=True) + "\n")
    write_json(output / "quality.json", [q.model_dump(mode="json") for q in result.qualidade])
    labels = Counter(r.rotulo.status_rotulo for r in result.registros)
    interest_events = [e for e in data.interacoes if e.tipo_evento == "interesse_demonstrado"]
    exposure_frequency = Counter(str(e.investidor_id) for e in data.exposicoes)
    startup_frequency = Counter(str(e.startup_id) for e in data.exposicoes)
    feature_groups = {k: len(v) for k, v in result.registros[0].features.model_dump().items()}
    missing = Counter(key for r in result.registros for key, value in r.features.ausentes.items() if value)
    segments, stages = Counter(), Counter()
    for row in result.registros:
        segments[row.features.categoricas["startup.segmento"]] += 1
        stages[row.features.categoricas["startup.estagio"]] += 1
    # Diagnóstico apenas: nunca retorna ao gerador ou à seleção de classes.
    from app.rules import rank
    from app.schemas import RulesRequest
    high_without_interest = partial_with_interest = 0
    for row in result.registros:
        snap = first_by_id[row.metadados["exposicao_id"]]
        score = rank(RulesRequest(investidor=snap.investidor, startups=[snap.startup], limite=1)).recomendacoes[0].score
        high_without_interest += score is not None and score >= .8 and row.rotulo.target == 0
        partial_with_interest += score is not None and score < .8 and row.rotulo.target == 1
    summary = {
        "config": {"seed": config.seed, "exposures": config.exposures, "cutoff": config.cutoff.isoformat()},
        "proveniencia": provenance, "qualidade_perfis": quality,
        "investidores_utilizados": len(exposure_frequency), "startups_utilizadas": len(startup_frequency),
        "exposicoes": len(data.exposicoes), "pares_unicos": len(result.registros),
        "exposicoes_repetidas": len(data.exposicoes) - len(result.registros),
        "eventos_interesse": len(interest_events), "eventos_total": len(data.interacoes),
        "labels": dict(labels), "labels_indefinidos": sum(r.rotulo.target is None for r in result.registros),
        "taxa_interesse_por_par": len(interest_events) / len(result.registros),
        "taxa_positivos_rotulados": labels["positivo"] / (labels["positivo"] + labels["negativo"]) if labels["positivo"] + labels["negativo"] else None,
        "features": feature_groups, "features_ausentes": dict(sorted(missing.items())),
        "registros_descartados_pipeline": len({(e.investidor_id, e.startup_id) for e in data.exposicoes}) - len(result.registros),
        "avisos_pipeline": dict(Counter(q.codigo for q in result.qualidade)),
        "distribuicao_segmentos": dict(sorted(segments.items())), "distribuicao_estagios": dict(sorted(stages.items())),
        "frequencia_exposicao_investidor": {"min": min(exposure_frequency.values()), "max": max(exposure_frequency.values())},
        "frequencia_exposicao_startup": {"min": min(startup_frequency.values()), "max": max(startup_frequency.values())},
        "diagnostico_1a": {"score_alto_sem_interesse": high_without_interest, "score_parcial_com_interesse": partial_with_interest},
        "limitacoes": ["Comportamento integralmente simulado; não comprova generalização para usuários reais.",
                        "Snapshots copiam os perfis atuais para um relógio fictício; não são reconstruções históricas.",
                        "historico_confirmado e historico_completo se referem somente ao mundo simulado.",
                        "Não há garantia de desfechos históricos reais, rejeição explícita ou propensões de exposição reais.",
                        "training.jsonl exclui targets nulos; requer pré-processamento e divisão apropriada antes de treinar."]}
    write_json(output / "summary.json", summary)
    manifest = {path.name: file_hash(path) for path in sorted(output.iterdir()) if path.is_file()}
    write_json(output / "manifest.json", {"sha256": manifest, "origem_dados": "sintetica"})
    validate_exports(output)
    return summary


def validate_exports(output: Path):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    for filename, expected in manifest["sha256"].items():
        if Path(filename).name != filename or file_hash(output / filename) != expected:
            raise ValueError("Integridade inválida: " + filename)
    data = DatasetInput.model_validate_json((output / "input.json").read_bytes())
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    if data.origem_dados != "sintetica" or len(data.exposicoes) != summary["exposicoes"]:
        raise ValueError("Contrato ou quantidade de exposições inconsistente")
    audit_count = train_count = 0
    with (output / "dataset.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = DatasetRow.model_validate_json(line)
            if row.metadados["origem_dados"] != "sintetica":
                raise ValueError("Origem inválida")
            audit_count += 1
    with (output / "training.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if set(record) != {"features", "target"} or record["target"] not in (0, 1):
                raise ValueError("Registro de treinamento inválido")
            train_count += 1
    if audit_count != summary["pares_unicos"] or train_count != audit_count - summary["labels_indefinidos"]:
        raise ValueError("Contagens de exportação inconsistentes")
    return {"audit_rows": audit_count, "training_rows": train_count, "hashes_validos": True}
