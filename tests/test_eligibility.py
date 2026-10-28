from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.rules import rank, WEIGHTS
from app.schemas import RulesRequest

I = "11111111-1111-4111-8111-111111111111"
S = "22222222-2222-4222-8222-222222222222"
UI = "33333333-3333-4333-8333-333333333333"
US = "44444444-4444-4444-8444-444444444444"


@pytest.fixture
def payload():
    return {"investidor": {"id": I, "segmentosInteresse": ["agtech"],
                          "estagiosInteresse": ["mvp"], "regioesInteresse": ["nordeste"],
                          "modelosInteresse": ["b2b"], "areasAjuda": ["mentoria"]},
            "startups": [{"id": S, "segmento": "agtech", "estagio": "mvp",
                          "regioesAtuacao": ["nordeste"], "modeloNegocio": "b2b",
                          "necessidadesAdicionais": ["mentoria"]}]}


def response(payload):
    return rank(RulesRequest.model_validate(payload))


def operational(payload):
    payload["investidor"]["usuario"] = {"id": UI, "ativo": True}
    payload["startups"][0].update(usuario={"id": US, "ativo": True}, statusModeracao="aprovado")
    return payload


def test_legacy_indeterminate_preserves_scores(payload):
    r = response(payload)
    item = r.recomendacoes[0]
    assert item.elegibilidade.estado == "indeterminado"
    assert len(item.elegibilidade.pendencias) == 5
    assert item.elegibilidade.impedimentos == []
    assert item.score == pytest.approx(1)
    assert item.cobertura == pytest.approx(1)
    assert item.scoreRanking == pytest.approx(1)
    assert r.excluidas == []


def test_all_operational_conditions_verified(payload):
    r = response(operational(payload)).recomendacoes[0]
    assert r.elegibilidade.estado == "elegivel"
    assert not r.elegibilidade.pendencias
    assert not r.elegibilidade.impedimentos
    assert len(r.elegibilidade.verificadas) == 6


@pytest.mark.parametrize("status", ["pendente", "rejeitado", "suspenso"])
def test_explicit_moderation_blocks_even_with_missing_data(payload, status):
    payload["startups"][0]["statusModeracao"] = status
    r = response(payload)
    assert r.recomendacoes == []
    assert r.excluidas[0].elegibilidade.estado == "inelegivel"
    assert status in r.excluidas[0].elegibilidade.impedimentos[0]
    assert r.excluidas[0].elegibilidade.pendencias


@pytest.mark.parametrize("side", ["investidor", "startup"])
def test_inactive_user_blocks(payload, side):
    target = payload["investidor"] if side == "investidor" else payload["startups"][0]
    target["usuario"] = {"ativo": False}
    r = response(payload)
    assert not r.recomendacoes
    assert "inativo" in r.excluidas[0].elegibilidade.impedimentos[0]


@pytest.mark.parametrize("side", ["investidor", "startup"])
def test_profile_user_id_collision_blocks(payload, side):
    target = payload["investidor"] if side == "investidor" else payload["startups"][0]
    target["usuario"] = {"id": target["id"]}
    assert response(payload).excluidas[0].elegibilidade.estado == "inelegivel"


def test_partial_operational_information_is_not_approval(payload):
    payload["startups"][0]["statusModeracao"] = "aprovado"
    item = response(payload).recomendacoes[0]
    assert item.elegibilidade.estado == "indeterminado"
    assert item.score == pytest.approx(1)


@pytest.mark.parametrize("mode", ["mentor", "anjo_mentor"])
def test_support_modes_without_financial_data(payload, mode):
    baseline = response(payload).recomendacoes[0]
    payload["investidor"]["tipoInvestidor"] = mode
    r = response(payload)
    item = r.recomendacoes[0]
    assert r.tipoInvestidor == mode
    assert item.criterios == baseline.criterios
    assert item.score == baseline.score
    assert item.cobertura == baseline.cobertura
    assert item.scoreRanking == baseline.scoreRanking
    assert not r.excluidas


def test_angel_does_not_imply_mentoring(payload):
    payload["investidor"]["tipoInvestidor"] = "anjo"
    r = response(payload)
    item = r.recomendacoes[0]
    assert not r.excluidas
    assert item.criterios["ajuda"].score is None
    assert item.criterios["ajuda"].cobertura == 0
    assert item.score == pytest.approx(1)
    assert item.cobertura == pytest.approx(.9)
    assert item.scoreRanking == pytest.approx(.95)
    assert "ajuda" not in {j.criterio for j in item.justificativas}
    assert r.pesos == dict(WEIGHTS)


def test_anjo_with_only_support_has_no_artificial_score(payload):
    payload["investidor"] = {"id": I, "tipoInvestidor": "anjo", "areasAjuda": ["mentoria"]}
    item = response(payload).recomendacoes[0]
    assert item.score is None and item.scoreRanking is None
    assert item.cobertura == 0


def test_eligibility_does_not_change_legacy_ranking(payload):
    second = deepcopy(payload["startups"][0])
    second.update(id="55555555-5555-4555-8555-555555555555", estagio="escala")
    payload["startups"].append(second)
    baseline = response(payload).recomendacoes
    operational(payload)
    payload["startups"][1].update(usuario={"id": US, "ativo": True}, statusModeracao="aprovado")
    current = response(payload).recomendacoes
    assert [(r.startupId, r.score, r.cobertura, r.scoreRanking) for r in current] == [
        (r.startupId, r.score, r.cobertura, r.scoreRanking) for r in baseline]


def test_exclusion_before_limit_and_positions(payload):
    second = deepcopy(payload["startups"][0])
    second["id"] = "55555555-5555-4555-8555-555555555555"
    payload["startups"][0]["statusModeracao"] = "rejeitado"
    payload["startups"].append(second)
    payload["limite"] = 1
    r = response(payload)
    assert len(r.recomendacoes) == len(r.excluidas) == 1
    assert str(r.recomendacoes[0].startupId) == second["id"]
    assert r.recomendacoes[0].posicao == 1


@pytest.mark.parametrize("key", ["bio", "descricaoExperiencia", "setoresAtuacao"])
def test_professional_history_is_not_structured_intention(payload, key):
    payload["investidor"][key] = "fintech" if key != "setoresAtuacao" else ["fintech"]
    with pytest.raises(ValidationError):
        RulesRequest.model_validate(payload)


@pytest.mark.parametrize("value", ["false", "true", 0, 1])
def test_active_requires_real_boolean(payload, value):
    payload["investidor"]["usuario"] = {"ativo": value}
    with pytest.raises(ValidationError):
        RulesRequest.model_validate(payload)


@pytest.mark.parametrize("field,value", [("tipoInvestidor", "venture_capital"), ("statusModeracao", "approved")])
def test_invalid_new_enum(payload, field, value):
    target = payload["investidor"] if field == "tipoInvestidor" else payload["startups"][0]
    target[field] = value
    with pytest.raises(ValidationError):
        RulesRequest.model_validate(payload)


def test_http_additive_schema_and_explicit_exclusion(payload):
    with TestClient(app) as client:
        old = client.post("/match/rules", json=payload)
        assert old.status_code == 200
        assert old.json()["recomendacoes"][0]["elegibilidade"]["estado"] == "indeterminado"
        payload["startups"][0]["statusModeracao"] = "suspenso"
        blocked = client.post("/match/rules", json=payload)
        assert blocked.status_code == 200
        assert not blocked.json()["recomendacoes"]
        assert blocked.json()["excluidas"][0]["elegibilidade"]["estado"] == "inelegivel"
        operational(payload)
        assert client.post("/match/rules", json=payload).json()["recomendacoes"][0]["elegibilidade"]["estado"] == "elegivel"
