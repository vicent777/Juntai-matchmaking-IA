from copy import deepcopy
from itertools import permutations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.rules import rank, WEIGHTS
from app.schemas import RulesRequest

INVESTOR = "11111111-1111-4111-8111-111111111111"
STARTUP = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def payload():
    return {
        "investidor": {"id": INVESTOR, "segmentosInteresse": ["agtech"],
                       "estagiosInteresse": ["mvp"], "regioesInteresse": ["nordeste"],
                       "modelosInteresse": ["b2b"], "areasAjuda": ["mentoria"]},
        "startups": [{"id": STARTUP, "segmento": "agtech", "segmentosSecundarios": [],
                      "estagio": "mvp", "regioesAtuacao": ["nordeste"],
                      "modeloNegocio": "b2b", "necessidadesAdicionais": ["mentoria"]}],
        "limite": 5,
    }


def result(payload):
    return rank(RulesRequest.model_validate(payload)).recomendacoes[0]


def test_complete(payload):
    r = result(payload)
    assert r.score == pytest.approx(1)
    assert r.cobertura == pytest.approx(1)
    assert r.criteriosAvaliados == 5
    assert len(r.justificativas) == 5
    assert r.avisos == []


def test_partial_weighted_score(payload):
    payload["startups"][0]["estagio"] = "escala"
    r = result(payload)
    assert r.score == pytest.approx(.75)
    assert r.criterios["estagio"].estado == "incompativel"
    assert "estagio" not in {j.criterio for j in r.justificativas}


def test_all_incompatible(payload):
    payload["startups"][0].update(segmento="fintech", estagio="escala",
                                  regioesAtuacao=["sul"], modeloNegocio="b2c",
                                  necessidadesAdicionais=["contratacao_talentos"])
    r = result(payload)
    assert r.score == 0
    assert r.cobertura == pytest.approx(1)
    assert r.justificativas == []


def test_missing_renormalizes(payload):
    payload["startups"][0].pop("estagio")
    r = result(payload)
    assert r.score == pytest.approx(1)
    assert r.cobertura == pytest.approx(.75)
    assert r.criteriosAvaliados == 4
    assert r.criterios["estagio"].score is None
    assert r.avisos


def test_no_evaluable_criteria():
    r = result({"investidor": {"id": INVESTOR}, "startups": [{"id": STARTUP}]})
    assert r.score is None
    assert r.scoreRanking is None
    assert r.cobertura == 0
    assert r.criteriosAvaliados == 0
    assert r.justificativas == []


def test_empty_preferences_are_unknown(payload):
    for key in list(payload["investidor"]):
        if key != "id":
            payload["investidor"][key] = []
    assert result(payload).score is None


@pytest.mark.parametrize("field", ["segmento", "estagio", "modeloNegocio"])
def test_null_scalar_is_unknown(payload, field):
    payload["startups"][0][field] = None
    assert result(payload).criteriosAvaliados == 4


@pytest.mark.parametrize("side,field,value", [
    ("investidor", "segmentosInteresse", ["climatech"]),
    ("investidor", "estagiosInteresse", ["seed"]),
    ("investidor", "regioesInteresse", ["nacional"]),
    ("investidor", "modelosInteresse", ["saas"]),
    ("investidor", "areasAjuda", ["conexoes_mercado"]),
    ("startup", "necessidadesAdicionais", ["networking"]),
    ("startup", "segmento", "climatech"),
    ("startup", "estagio", "seed"),
    ("startup", "regioesAtuacao", ["nacional"]),
    ("startup", "modeloNegocio", "saas"),
])
def test_invalid_enums(payload, side, field, value):
    target = payload["investidor"] if side == "investidor" else payload["startups"][0]
    target[field] = value
    with pytest.raises(ValidationError):
        RulesRequest.model_validate(payload)


def test_secondary_segment_matches_without_penalty(payload):
    payload["startups"][0].update(segmento="fintech", segmentosSecundarios=["agtech", "agtech"])
    r = result(payload)
    assert r.criterios["segmento"].score == 1
    assert r.criterios["segmento"].evidencias == ["agtech"]


def test_missing_primary_cannot_prove_mismatch(payload):
    payload["startups"][0].update(segmento=None, segmentosSecundarios=["fintech"])
    assert result(payload).criterios["segmento"].score is None


@pytest.mark.parametrize("need,area", [("mentoria", "mentoria"), ("conexoes_mercado", "networking"),
                                      ("contratacao_talentos", "rh_pessoas")])
def test_help_equivalences(payload, need, area):
    payload["investidor"]["areasAjuda"] = [area]
    payload["startups"][0]["necessidadesAdicionais"] = [need]
    assert result(payload).criterios["ajuda"].score == 1


def test_help_fraction_and_duplicates(payload):
    payload["startups"][0]["necessidadesAdicionais"] = ["mentoria", "mentoria", "conexoes_mercado"]
    r = result(payload)
    assert r.criterios["ajuda"].score == .5
    assert r.criterios["ajuda"].estado == "parcial"
    assert r.score == pytest.approx(.95)


@pytest.mark.parametrize("needs", [["outro"], ["parcerias_estrategicas"]])
def test_unmapped_help_is_unknown(payload, needs):
    payload["startups"][0]["necessidadesAdicionais"] = needs
    r = result(payload)
    assert r.criterios["ajuda"].score is None
    assert r.cobertura == pytest.approx(.9)
    assert "ajuda" not in {j.criterio for j in r.justificativas}


def test_any_region_overlap_and_order_invariance(payload):
    payload["startups"][0]["regioesAtuacao"] = ["sul", "nordeste", "nordeste"]
    assert result(payload).criterios["regiao"].score == 1


def test_ranking_coverage_uuid_unknown_and_limit(payload):
    complete = payload["startups"][0]
    tie = deepcopy(complete)
    tie["id"] = "33333333-3333-4333-8333-333333333333"
    sparse = {"id": "44444444-4444-4444-8444-444444444444", "segmento": "agtech"}
    mismatch = deepcopy(complete)
    mismatch["id"] = "55555555-5555-4555-8555-555555555555"
    mismatch["estagio"] = "escala"
    unknown = {"id": "66666666-6666-4666-8666-666666666666"}
    expected = [complete["id"], tie["id"], mismatch["id"], sparse["id"], unknown["id"]]
    for order in permutations([complete, tie, sparse, mismatch, unknown]):
        payload["startups"] = list(order)
        response = rank(RulesRequest.model_validate(payload))
        assert [str(r.startupId) for r in response.recomendacoes] == expected
        assert [r.posicao for r in response.recomendacoes] == [1, 2, 3, 4, 5]
    payload["limite"] = 2
    assert len(rank(RulesRequest.model_validate(payload)).recomendacoes) == 2


@pytest.mark.parametrize("limit", [0, -1, 1001, True, "5", 1.5])
def test_invalid_limits(payload, limit):
    payload["limite"] = limit
    with pytest.raises(ValidationError):
        RulesRequest.model_validate(payload)


def test_empty_candidates(payload):
    payload["startups"] = []
    assert rank(RulesRequest.model_validate(payload)).recomendacoes == []


def test_duplicate_ids_rejected(payload):
    payload["startups"] *= 2
    with pytest.raises(ValidationError):
        RulesRequest.model_validate(payload)


def test_explanations_and_bounds(payload):
    for stage in [None, "mvp", "escala"]:
        for needs in [[], ["outro"], ["mentoria"], ["mentoria", "conexoes_mercado"]]:
            payload["startups"][0].update(estagio=stage, necessidadesAdicionais=needs)
            r = result(payload)
            assert r.score is None or 0 <= r.score <= 1
            assert r.scoreRanking is None or 0 <= r.scoreRanking <= 1
            assert 0 <= r.cobertura <= 1
            positives = {k for k, c in r.criterios.items() if c.score is not None and c.score > 0}
            assert {j.criterio for j in r.justificativas} == positives
            for j in r.justificativas:
                assert j.evidencias == r.criterios[j.criterio].evidencias
                assert j.evidencias


def test_server_weight_configuration(payload):
    weights = dict(WEIGHTS, estagio=75)
    payload["startups"][0]["estagio"] = "escala"
    response = rank(RulesRequest.model_validate(payload), weights)
    assert response.recomendacoes[0].score == pytest.approx(.5)


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), True])
def test_invalid_weights(payload, bad):
    with pytest.raises(ValueError):
        rank(RulesRequest.model_validate(payload), dict(WEIGHTS, segmento=bad))


def test_http(payload):
    with TestClient(app) as client:
        response = client.post("/match/rules", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["investidorId"] == INVESTOR
        assert body["recomendacoes"][0]["startupId"] == STARTUP
        assert body["recomendacoes"][0]["score"] == pytest.approx(1)
        assert body["recomendacoes"][0]["scoreRanking"] == pytest.approx(1)
        assert client.get("/").json() == {"mensagem": "API de matchmaking funcionando!"}
        assert client.get("/health").json() == {"status": "ok"}
        payload["investidor"]["id"] = "not-a-uuid"
        assert client.post("/match/rules", json=payload).status_code == 422


def test_http_unknown_and_reject_full_entities(payload):
    with TestClient(app) as client:
        response = client.post("/match/rules", json={"investidor": {"id": INVESTOR}, "startups": [{"id": STARTUP}]})
        assert response.status_code == 200
        assert response.json()["recomendacoes"][0]["score"] is None
        assert response.json()["recomendacoes"][0]["scoreRanking"] is None
        payload["investidor"]["usuarioId"] = INVESTOR
        assert client.post("/match/rules", json=payload).status_code == 422


@pytest.mark.parametrize("areas,expected", [(["mentoria"], 1.0), (["networking"], 0.0)])
def test_mixed_needs_partial_coverage(payload, areas, expected):
    payload["investidor"]["areasAjuda"] = areas
    payload["startups"][0]["necessidadesAdicionais"] = ["mentoria", "outro", "outro"]
    r = result(payload)
    help_result = r.criterios["ajuda"]
    assert help_result.score == expected
    assert help_result.cobertura == .5
    assert help_result.avaliacaoParcial is True
    assert "outro" in help_result.aviso
    assert r.cobertura == pytest.approx(.95)
    assert r.criteriosAvaliados == 5
    assert r.score == pytest.approx(.9 + .1 * expected)
    assert r.scoreRanking == pytest.approx(r.score * .975)
    assert any("Cobertura incompleta" in warning for warning in r.avisos)
    assert help_result.evidencias == (["mentoria <- mentoria"] if expected else [])
    assert ("ajuda" in {j.criterio for j in r.justificativas}) == bool(expected)


def test_mixed_needs_known_fraction_and_coverage(payload):
    payload["startups"][0]["necessidadesAdicionais"] = ["mentoria", "conexoes_mercado", "outro"]
    r = result(payload)
    assert r.criterios["ajuda"].score == .5
    assert r.criterios["ajuda"].estado == "parcial"
    assert r.criterios["ajuda"].cobertura == pytest.approx(2 / 3)
    assert r.cobertura == pytest.approx(.9 + .1 * 2 / 3)
    assert r.score == pytest.approx(.95)


def test_only_help_partially_evaluable(payload):
    payload["investidor"] = {"id": INVESTOR, "areasAjuda": ["mentoria"]}
    payload["startups"][0]["necessidadesAdicionais"] = ["mentoria", "outro"]
    r = result(payload)
    assert r.score == 1
    assert r.cobertura == pytest.approx(.05)
    assert r.scoreRanking == pytest.approx(.525)


def test_required_ranking_scenario(payload):
    startup_b = deepcopy(payload["startups"][0])
    startup_b["id"] = "33333333-3333-4333-8333-333333333333"
    startup_b["modeloNegocio"] = "b2c"
    startup_a = {"id": STARTUP, "segmento": "agtech"}
    for order in ([startup_a, startup_b], [startup_b, startup_a]):
        payload["startups"] = order
        b, a = rank(RulesRequest.model_validate(payload)).recomendacoes
        assert str(b.startupId) == startup_b["id"]
        assert (a.score, a.cobertura, a.scoreRanking) == pytest.approx((1, .30, .65))
        assert (b.score, b.cobertura, b.scoreRanking) == pytest.approx((.85, 1, .85))


def test_http_partial_help(payload):
    payload["startups"][0]["necessidadesAdicionais"] = ["mentoria", "outro"]
    with TestClient(app) as client:
        response = client.post("/match/rules", json=payload)
        assert response.status_code == 200
        r = response.json()["recomendacoes"][0]
        assert r["criterios"]["ajuda"]["avaliacaoParcial"] is True
        assert r["criterios"]["ajuda"]["cobertura"] == .5
        assert r["scoreRanking"] == pytest.approx(.975)
