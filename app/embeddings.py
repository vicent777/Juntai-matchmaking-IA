"""Adaptador lazy: importar a API ou coletar testes nunca baixa pesos."""
from math import fsum, hypot, isfinite
from threading import Lock
from typing import Protocol, Sequence

MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class EmbeddingError(RuntimeError):
    pass


class Encoder(Protocol):
    model_id: str

    def encode(self, texts: list[str]) -> Sequence[Sequence[float]]: ...


def unit_vector(vector) -> list[float] | None:
    values = [float(value) for value in vector]
    if not values or not all(isfinite(value) for value in values):
        return None
    norm = hypot(*values)
    if not norm or not isfinite(norm):
        return None
    return [value / norm for value in values]


def load_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_ID, device="cpu", trust_remote_code=False)


class LocalEncoder:
    model_id = MODEL_ID

    def __init__(self):
        self._model = None
        self._lock = Lock()

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # Serializa também inferência para limitar uso concorrente de CPU/memória.
        with self._lock:
            try:
                if self._model is None:
                    self._model = load_model()
                model = self._model
                size = model.max_seq_length - model.tokenizer.num_special_tokens_to_add(pair=False)
                if size < 1:
                    raise ValueError("Limite de tokens inválido.")
                result = []
                for text in texts:
                    tokens = model.tokenizer.encode(text, add_special_tokens=False)
                    chunks = [model.tokenizer.decode(tokens[n:n + size], skip_special_tokens=True)
                              for n in range(0, len(tokens), size)]
                    if not chunks:
                        raise ValueError("Texto sem tokens.")
                    vectors = model.encode(chunks, batch_size=32, show_progress_bar=False,
                                           normalize_embeddings=True, convert_to_numpy=True)
                    # Média ponderada pelos tokens: o bloco final curto não domina.
                    lengths = [min(size, len(tokens) - n) for n in range(0, len(tokens), size)]
                    mean = [fsum(float(v[d]) * weight for v, weight in zip(vectors, lengths)) / sum(lengths)
                            for d in range(len(vectors[0]))]
                    normalized = unit_vector(mean)
                    if normalized is None:
                        raise ValueError("Embedding inválido.")
                    result.append(normalized)
                return result
            except Exception as exc:
                raise EmbeddingError("Não foi possível gerar embeddings locais.") from exc


# Instância leve; o modelo é carregado apenas em encode(), uma vez por processo.
_encoder = LocalEncoder()


def get_encoder() -> Encoder:
    return _encoder
