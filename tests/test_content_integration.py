"""Nunca carrega modelo na coleta; só roda mediante opção explícita."""
import pytest

from app.content import rank_content
from app.content_schemas import ContentRequest
from app.embeddings import get_encoder


def test_real_multilingual_model(request):
    if not request.config.getoption("--run-real-embeddings"):
        pytest.skip("Modelo real exige --run-real-embeddings; pode baixar pesos.")
    payload = ContentRequest.model_validate({
        "investidor": {"id": "11111111-1111-4111-8111-111111111111",
                       "bio": "Busco soluções digitais para agricultura e pequenos produtores rurais."},
        "startups": [
            {"id": "22222222-2222-4222-8222-222222222222",
             "descricaoPitch": "Tecnologia agrícola para apoiar agricultores familiares no campo."},
            {"id": "33333333-3333-4333-8333-333333333333",
             "descricaoPitch": "Estúdio de jogos eletrônicos de combate espacial para consoles."},
        ],
    })
    response = rank_content(payload, get_encoder())
    assert str(response.recomendacoes[0].startupId) == str(payload.startups[0].id)
    assert response.recomendacoes[0].score > response.recomendacoes[1].score
    assert all(r.score is not None and 0 <= r.score <= 1 for r in response.recomendacoes)
