from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from itertools import permutations
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import embeddings
from app.content import rank_content
from app.content_schemas import ContentRequest
from app.content_text import combine, investor_text, startup_text
from app.embeddings import EmbeddingError, LocalEncoder, get_encoder
from app.main import app

INVESTOR = "11111111-1111-4111-8111-111111111111"
STARTUP = "22222222-2222-4222-8222-222222222222"


class FakeEncoder:
    model_id = "simulado-testes"

    def __init__(self):
        self.calls = []

    def encode(self, texts):
        self.calls.append(list(texts))
        # Vetores controlados representam paráfrases e um tema não relacionado.
        return [[1, 0] if "agricultura" in text else [.8, .6] if "produtores" in text
                else [0, 1] for text in texts]


@pytest.fixture
def payload():
    return {"investidor": {"id": INVESTOR, "bio": "Tecnologia para agricultura familiar"},
            "startups": [{"id": STARTUP, "descricaoPitch": "Soluções digitais para produtores rurais"}]}


def test_semantic_similarity_and_unrelated_ranking(payload):
    unrelated = {"id": "33333333-3333-4333-8333-333333333333", "descricaoPitch": "Jogos eletrônicos de aventura espacial"}
    payload["startups"].append(unrelated)
    encoder = FakeEncoder()
    response = rank_content(ContentRequest.model_validate(payload), encoder)
    near, far = response.recomendacoes
    assert str(near.startupId) == STARTUP
    assert near.similaridadeBruta == pytest.approx(.8)
    assert near.score == pytest.approx(.9)
    assert far.similaridadeBruta == pytest.approx(0)
    assert far.score == pytest.approx(.5)
    assert len(encoder.calls) == 1
    assert len(encoder.calls[0]) == 3
    assert response.modeloEmbeddings == encoder.model_id


def test_text_normalization_deduplication_and_canvas_selection(payload):
    payload["investidor"]["descricaoExperiencia"] = "  TECNOLOGIA para agricultura   familiar "
    payload["startups"][0].update(
        descricaoCurta="  Soluções digitais para produtores rurais ",
        mercadoAlvo="Cooperativas de produtores",
        canvasJson={"problema": "Acesso limitado ao mercado", "solucao": "Conectar produtores aos compradores",
                    "value": "Mais acesso ao mercado", "customers": "Cooperativas de produtores",
                    "costs": "Não incluir custos", "partners": "Não incluir parceiros", "activities": ["Não incluir"],
                    "revenue": 123})
    request = ContentRequest.model_validate(payload)
    assert investor_text(request.investidor) == "Tecnologia para agricultura familiar"
    text = startup_text(request.startups[0])
    assert text.count("Soluções digitais") == 1
    assert text.count("Cooperativas de produtores") == 1
    assert "Acesso limitado" in text and "Conectar produtores" in text and "Mais acesso" in text
    assert "Não incluir" not in text
    assert combine([None, "", " \n\t ", {"x": 1}, "Olá  mundo", "OLÁ MUNDO"]) == "Olá mundo"


@pytest.mark.parametrize("text", [None, "", "  \n ", "agtech", "123 456", "!? ..."])
def test_insufficient_investor_does_not_encode(payload, text):
    payload["investidor"]["bio"] = text
    encoder = FakeEncoder()
    response = rank_content(ContentRequest.model_validate(payload), encoder)
    r = response.recomendacoes[0]
    assert r.score is None and r.similaridadeBruta is None and r.avisos
    assert response.avisos
    assert encoder.calls == []


def test_empty_startup_and_absent_fields(payload):
    payload["startups"] = [{"id": STARTUP}]
    encoder = FakeEncoder()
    r = rank_content(ContentRequest.model_validate(payload), encoder).recomendacoes[0]
    assert r.score is None and r.avisos
    assert not encoder.calls
    payload["startups"] = []
    assert rank_content(ContentRequest.model_validate(payload), encoder).recomendacoes == []


def test_deterministic_order_limit_and_duplicate_texts(payload):
    first = payload["startups"][0]
    second = dict(first, id="33333333-3333-4333-8333-333333333333")
    unknown = {"id": "44444444-4444-4444-8444-444444444444"}
    for order in permutations([first, second, unknown]):
        payload["startups"] = list(order)
        encoder = FakeEncoder()
        response = rank_content(ContentRequest.model_validate(payload), encoder)
        assert [str(r.startupId) for r in response.recomendacoes] == [first["id"], second["id"], unknown["id"]]
        assert [r.posicao for r in response.recomendacoes] == [1, 2, 3]
        assert len(encoder.calls[0]) == 2
    payload["limite"] = 1
    assert len(rank_content(ContentRequest.model_validate(payload), FakeEncoder()).recomendacoes) == 1


@pytest.mark.parametrize("vector,raw,score", [([1, 0], 1, 1), ([-1, 0], -1, 0), ([0, 1], 0, .5)])
def test_cosine_bounds_and_normalization(payload, vector, raw, score):
    class Fixed(FakeEncoder):
        def encode(self, texts):
            return [[10, 0], vector]
    r = rank_content(ContentRequest.model_validate(payload), Fixed()).recomendacoes[0]
    assert r.similaridadeBruta == pytest.approx(raw)
    assert r.score == pytest.approx(score)


@pytest.mark.parametrize("vector", [[0, 0], [float("nan"), 1], [float("inf"), 0], []])
def test_invalid_vectors_are_unavailable(payload, vector):
    class Invalid(FakeEncoder):
        def encode(self, texts):
            return [[1, 0], vector]
    r = rank_content(ContentRequest.model_validate(payload), Invalid()).recomendacoes[0]
    assert r.score is None and r.avisos


def test_invalid_encoder_shape(payload):
    class Invalid(FakeEncoder):
        def encode(self, texts):
            return [[1, 0], [1, 0, 0]]
    with pytest.raises(EmbeddingError):
        rank_content(ContentRequest.model_validate(payload), Invalid())


class FakeTokenizer:
    def num_special_tokens_to_add(self, pair=False):
        return 2

    def encode(self, text, add_special_tokens=False):
        return list(range(len(text.split())))

    def decode(self, tokens, skip_special_tokens=True):
        return " ".join(str(token) for token in tokens)


class FakeModel:
    max_seq_length = 6
    tokenizer = FakeTokenizer()

    def __init__(self):
        self.chunks = []

    def encode(self, chunks, **kwargs):
        self.chunks.extend(chunks)
        assert kwargs["normalize_embeddings"] is True
        return [[1, 0] for _ in chunks]


def test_lazy_model_reuse_concurrency_and_chunking(monkeypatch):
    loaded = []
    model = FakeModel()

    def load():
        loaded.append(True)
        return model

    monkeypatch.setattr(embeddings, "load_model", load)
    encoder = LocalEncoder()
    assert loaded == []
    assert encoder.encode([]) == [] and loaded == []
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: encoder.encode(["um dois três quatro cinco seis sete oito nove"]), range(3)))
    assert len(loaded) == 1
    assert all(result == [[1, 0]] for result in results)
    assert model.chunks[:3] == ["0 1 2 3", "4 5 6 7", "8"]
    assert get_encoder() is get_encoder()


def test_model_failure_is_wrapped_without_details(monkeypatch):
    def fail():
        raise OSError("detalhe interno de download")
    monkeypatch.setattr(embeddings, "load_model", fail)
    with pytest.raises(EmbeddingError, match="Não foi possível"):
        LocalEncoder().encode(["um dois três"])


def test_real_adapter_constructor_uses_cpu_without_remote_code(monkeypatch):
    calls = []
    model = FakeModel()

    def constructor(model_id, **kwargs):
        calls.append((model_id, kwargs))
        return model

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=constructor))
    encoder = LocalEncoder()
    assert calls == []
    encoder.encode(["um dois três"])
    encoder.encode(["quatro cinco seis"])
    assert calls == [(embeddings.MODEL_ID, {"device": "cpu", "trust_remote_code": False})]


def test_long_document_mean_is_weighted_by_chunk_length(monkeypatch):
    class WeightedModel(FakeModel):
        def encode(self, chunks, **kwargs):
            assert len(chunks) == 2
            return [[1, 0], [0, 1]]

    monkeypatch.setattr(embeddings, "load_model", lambda: WeightedModel())
    vector = LocalEncoder().encode(["um dois três quatro cinco"])[0]
    # Quatro tokens no primeiro bloco, um no último: direção (4, 1).
    assert vector == pytest.approx([4 / 17 ** .5, 1 / 17 ** .5])


def test_http_contract_and_unavailability(payload):
    encoder = FakeEncoder()
    app.dependency_overrides[get_encoder] = lambda: encoder
    try:
        with TestClient(app) as client:
            response = client.post("/match/content", json=payload)
            assert response.status_code == 200
            body = response.json()
            assert body["investidorId"] == INVESTOR
            assert body["recomendacoes"][0]["startupId"] == STARTUP
            assert body["recomendacoes"][0]["score"] == pytest.approx(.9)
            assert "justificativas" not in body["recomendacoes"][0]
            for invalid in [dict(payload, limite=0), dict(payload, limite=True), dict(payload, limite="3")]:
                assert client.post("/match/content", json=invalid).status_code == 422
            invalid = deepcopy(payload)
            invalid["investidor"]["id"] = "não-é-uuid"
            assert client.post("/match/content", json=invalid).status_code == 422
            invalid = deepcopy(payload)
            invalid["startups"] *= 2
            assert client.post("/match/content", json=invalid).status_code == 422
            invalid = deepcopy(payload)
            invalid["investidor"]["usuarioId"] = INVESTOR
            assert client.post("/match/content", json=invalid).status_code == 422
            payload["startups"] = [{"id": STARTUP}]
            assert client.post("/match/content", json=payload).json()["recomendacoes"][0]["score"] is None
    finally:
        app.dependency_overrides.pop(get_encoder, None)


def test_http_model_error_returns_503(payload):
    class Failed(FakeEncoder):
        def encode(self, texts):
            raise EmbeddingError("detalhe interno")
    app.dependency_overrides[get_encoder] = lambda: Failed()
    try:
        with TestClient(app) as client:
            response = client.post("/match/content", json=payload)
            assert response.status_code == 503
            assert response.json() == {"detail": "Serviço de embeddings indisponível."}
    finally:
        app.dependency_overrides.pop(get_encoder, None)
