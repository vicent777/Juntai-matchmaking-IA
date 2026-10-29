"""Cenários sintéticos determinísticos; sem HTTP, banco ou treinamento."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.rules import CRITERIA
from app.supervised import DatasetInput, build_dataset

I = "11111111-1111-4111-8111-111111111111"
S = "22222222-2222-4222-8222-222222222222"
S2 = "33333333-3333-4333-8333-333333333333"
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def event(day=5, id="1", **changes):
    return {"id": id, "investidor_id": I, "startup_id": S,
            "tipo_evento": "interesse_demonstrado", "ocorrido_em": T0 + timedelta(days=day), **changes}


@pytest.fixture
def payload():
    return {
        "origem_dados": "sintetica", "data_corte": T0 + timedelta(days=40),
        "historico_completo": True, "completo_ate": T0 + timedelta(days=40),
        "exposicoes": [{"exposicao_id": "e1", "investidor_id": I, "startup_id": S, "ocorrido_em": T0}],
        "snapshots": [{"exposicao_id": "e1", "estado_em": T0, "historico_confirmado": True,
                       "investidor": {"id": I, "tipoInvestidor": "anjo_mentor", "segmentosInteresse": ["agtech"],
                                      "ticketMinimo": "100.00", "ticketMaximo": "1000.00"},
                       "startup": {"id": S, "segmento": "agtech", "capitalProcurado": "5000.00"}}],
        "interacoes": [],
    }


def run(payload):
    return build_dataset(DatasetInput.model_validate(payload))


@pytest.mark.parametrize("day,cutoff,status,target", [
    (5, 40, "positivo", 1), (None, 40, "negativo", 0),
    (None, 10, "censurado", None), (-1, 40, "interesse_previo", None),
    (0, 40, "interesse_previo", None), (31, 40, "negativo", 0),
    (20, 10, "censurado", None), (30, 30, "positivo", 1),
    (None, 30, "negativo", 0), (1, 2, "positivo", 1),
])
def test_target_windows(payload, day, cutoff, status, target):
    payload["data_corte"] = T0 + timedelta(days=cutoff)
    payload["interacoes"] = [] if day is None else [event(day)]
    result = run(payload)
    assert result.registros[0].rotulo.status_rotulo == status
    assert result.registros[0].rotulo.target == target
    if day is not None and day > cutoff:
        assert "evento_futuro" in {q.codigo for q in result.qualidade}
        assert result.registros[0].auditoria["eventos_ids"] == []


def test_multiple_exposures_first_anchor(payload):
    later = {**payload["exposicoes"][0], "exposicao_id": "e2", "ocorrido_em": T0 + timedelta(days=10)}
    payload["exposicoes"].insert(0, later)
    assert run(payload).registros[0].metadados["exposicao_id"] == "e1"
    assert len(run(payload).registros) == 1


def test_order_and_first_interest(payload):
    payload["interacoes"] = [event(9, "later"), event(3, "first"), event(3, "first")]
    result = run(payload)
    assert result.registros[0].rotulo.evento_interesse_id == "first"
    assert result.registros[0].auditoria["eventos_ids"] == ["first", "later"]
    assert {"duplicata_id", "multiplos_interesses"} <= {q.codigo for q in result.qualidade}


def test_no_exposure(payload):
    payload.update(exposicoes=[], snapshots=[], interacoes=[event()])
    result = run(payload)
    assert result.registros == []
    assert result.qualidade[0].codigo == "interacao_sem_exposicao"


@pytest.mark.parametrize("case", ["missing", "future", "stale", "unconfirmed"])
def test_invalid_snapshots(payload, case):
    if case == "missing":
        payload["snapshots"] = []
    elif case == "unconfirmed":
        payload["snapshots"][0]["historico_confirmado"] = False
    else:
        payload["snapshots"][0]["estado_em"] = T0 + timedelta(days=1 if case == "future" else -1)
    result = run(payload)
    assert result.registros == []
    assert result.qualidade


def test_timezones_same_instant(payload):
    payload["snapshots"][0]["estado_em"] = "2025-12-31T21:00:00-03:00"
    payload["interacoes"] = [event(5, ocorrido_em="2026-01-06T02:00:00+02:00")]
    assert run(payload).registros[0].rotulo.target == 1


def test_missing_values_and_empty_arrays(payload):
    payload["snapshots"][0]["investidor"] = {"id": I}
    row = run(payload).registros[0]
    assert row.features.numericas["investidor.ticketMinimo"] is None
    assert row.features.ausentes["investidor.ticketMinimo"]
    assert row.features.ausentes["investidor.segmentosInteresse"]
    assert row.features.derivadas["segmento.score"] is None
    assert row.features.derivadas["segmento.estado"] == "insuficiente"


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "abc", "1.001", "1000000000000.00", True])
def test_invalid_money(payload, value):
    payload["snapshots"][0]["investidor"]["ticketMinimo"] = value
    with pytest.raises(ValidationError):
        run(payload)


def test_invalid_ticket_interval(payload):
    payload["snapshots"][0]["investidor"]["ticketMinimo"] = "2000"
    with pytest.raises(ValidationError):
        run(payload)


@pytest.mark.parametrize("interest", [False, True])
def test_incomplete_history_no_first_conversion_claim(payload, interest):
    payload.update(historico_completo=False, completo_ate=None)
    payload["interacoes"] = [event()] if interest else []
    row = run(payload).registros[0]
    assert row.rotulo.target is None
    assert row.rotulo.status_rotulo == "historico_incompleto"


def test_completeness_watermark(payload):
    payload["completo_ate"] = T0
    with pytest.raises(ValidationError):
        run(payload)


@pytest.mark.parametrize("field", ["exposure", "event", "cutoff", "snapshot"])
def test_naive_timestamps_rejected(payload, field):
    if field == "exposure":
        payload["exposicoes"][0]["ocorrido_em"] = "2026-01-01T00:00:00"
    elif field == "event":
        payload["interacoes"] = [event(ocorrido_em="2026-01-02T00:00:00")]
    elif field == "snapshot":
        payload["snapshots"][0]["estado_em"] = "2026-01-01T00:00:00"
    else:
        payload["data_corte"] = "2026-02-10T00:00:00"
    with pytest.raises(ValidationError):
        run(payload)


def test_pair_mismatch(payload):
    payload["snapshots"][0]["startup"]["id"] = S2
    with pytest.raises(ValueError, match="Par inconsistente"):
        run(payload)


@pytest.mark.parametrize("field", ["exposicoes", "interacoes", "snapshots"])
def test_conflicting_identifiers(payload, field):
    if field == "interacoes":
        payload[field] = [event()]
    duplicate = deepcopy(payload[field][0])
    if field == "snapshots":
        duplicate["historico_confirmado"] = False
    else:
        duplicate["ocorrido_em"] += timedelta(days=1)
    payload[field].append(duplicate)
    with pytest.raises(ValueError, match="ID conflitante"):
        run(payload)


def test_duplicate_exposure_reported(payload):
    payload["exposicoes"] *= 2
    result = run(payload)
    assert len(result.registros) == 1
    assert result.qualidade[0].codigo == "duplicata_exposicao_id"


def test_future_exposure(payload):
    payload["data_corte"] = T0 - timedelta(days=1)
    assert run(payload).registros == []
    assert run(payload).qualidade[0].codigo == "exposicao_futura"


def test_features_not_affected_by_events_and_level1_reused(payload):
    before = deepcopy(payload)
    base = run(payload).registros[0].features
    payload["interacoes"] = [event(), event(100, "future", metadados={"faturamentoMensal": 999999})]
    assert run(payload).registros[0].features == base
    data = DatasetInput.model_validate(payload)
    snapshot = data.snapshots[0]
    for name, calculate in CRITERIA.items():
        result = calculate(snapshot.investidor, snapshot.startup)
        assert base.derivadas[f"{name}.score"] == result.score
        assert base.derivadas[f"{name}.cobertura"] == result.cobertura
    assert before["snapshots"] == payload["snapshots"]
    assert base.derivadas["capital_por_ticket_maximo"] == 5


def test_two_startups_example(payload):
    second = {**payload["exposicoes"][0], "exposicao_id": "e2", "startup_id": S2}
    snapshot = deepcopy(payload["snapshots"][0])
    snapshot.update(exposicao_id="e2")
    snapshot["startup"].update(id=S2, segmento="fintech")
    payload["exposicoes"].append(second)
    payload["snapshots"].append(snapshot)
    payload["interacoes"] = [event()]
    result = run(payload)
    assert [r.rotulo.target for r in result.registros] == [1, 0]
    assert [r.features.derivadas["segmento.score"] for r in result.registros] == [1, 0]
    for row in result.registros:
        assert set(row.model_dump()) == {"metadados", "features", "rotulo", "auditoria"}
        assert "target" not in row.features.model_dump_json()
        assert I not in row.features.model_dump_json()
    assert DatasetInput.model_validate_json(DatasetInput.model_validate(payload).model_dump_json())


@pytest.mark.parametrize("change", ["id", "timestamp", "extra", "enum"])
def test_invalid_contracts(payload, change):
    if change == "id":
        del payload["exposicoes"][0]["investidor_id"]
    elif change == "timestamp":
        payload["interacoes"] = [event(ocorrido_em="invalid")]
    elif change == "enum":
        payload["snapshots"][0]["startup"]["segmento"] = "invalid"
    else:
        payload["snapshots"][0]["startup"]["target"] = 1
    with pytest.raises(ValidationError):
        run(payload)


def test_configurable_window_and_partial_help(payload):
    payload["janela_dias"] = 2
    payload["interacoes"] = [event(3)]
    snapshot = payload["snapshots"][0]
    snapshot["investidor"]["areasAjuda"] = ["mentoria"]
    snapshot["startup"]["necessidadesAdicionais"] = ["mentoria", "outro"]
    row = run(payload).registros[0]
    assert row.rotulo.target == 0
    assert row.features.derivadas["ajuda.parcial"] is True
    assert row.features.derivadas["ajuda.cobertura"] == .5
    assert row.features.derivadas["ajuda.score"] == 1


def test_first_missing_snapshot_not_replaced(payload):
    payload["exposicoes"].append({**payload["exposicoes"][0], "exposicao_id": "later",
                                 "ocorrido_em": T0 + timedelta(days=1)})
    payload["snapshots"][0].update(exposicao_id="later", estado_em=T0 + timedelta(days=1))
    assert run(payload).registros == []


def test_orphan_snapshot(payload):
    payload["exposicoes"] = []
    with pytest.raises(ValueError, match="Snapshot sem exposição"):
        run(payload)


def test_example_module():
    from app.supervised.example import synthetic_example

    result = synthetic_example()
    assert [r.rotulo.target for r in result.registros] == [1, 0]
    assert result.qualidade == []
