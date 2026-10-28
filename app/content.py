"""Ranking semântico independente de regras e do mecanismo de embeddings."""
from math import fsum

from app.content_schemas import ContentRequest, ContentResponse, ContentRecommendation
from app.content_text import investor_text, startup_text, sufficient
from app.embeddings import Encoder, EmbeddingError, unit_vector

VERSION = "1b-v1"


def rank_content(request: ContentRequest, encoder: Encoder) -> ContentResponse:
    investor = investor_text(request.investidor)
    texts = [startup_text(s) for s in request.startups]
    investor_ok = sufficient(investor)
    valid = [text for text in texts if sufficient(text)]
    vectors = {}
    if investor_ok and valid:
        # Uma única geração do investidor; deduplica textos iguais na requisição.
        unique = list(dict.fromkeys([investor, *valid]))
        encoded = encoder.encode(unique)
        if len(encoded) != len(unique):
            raise EmbeddingError("Quantidade de embeddings inválida.")
        vectors = {text: unit_vector(vector) for text, vector in zip(unique, encoded)}
        dimensions = {len(v) for v in vectors.values() if v is not None}
        if len(dimensions) > 1:
            raise EmbeddingError("Dimensões de embeddings inconsistentes.")
    recommendations = []
    for startup, text in zip(request.startups, texts):
        warnings = []
        raw = None
        if not investor_ok:
            warnings.append("Conteúdo textual insuficiente no perfil do investidor.")
        if not sufficient(text):
            warnings.append("Conteúdo textual insuficiente no perfil da startup.")
        if not warnings:
            a, b = vectors.get(investor), vectors.get(text)
            if a is None or b is None:
                warnings.append("Embedding nulo ou inválido; similaridade indisponível.")
            else:
                raw = max(-1.0, min(1.0, fsum(x * y for x, y in zip(a, b))))
        recommendations.append(ContentRecommendation(
            startupId=startup.id, posicao=1, similaridadeBruta=raw,
            score=(raw + 1) / 2 if raw is not None else None, avisos=warnings,
        ))
    recommendations.sort(key=lambda r: (r.score is None, -(r.score or 0), str(r.startupId)))
    selected = recommendations[:request.limite]
    for position, recommendation in enumerate(selected, 1):
        recommendation.posicao = position
    warnings = [] if investor_ok else ["Conteúdo textual insuficiente no perfil do investidor."]
    return ContentResponse(investidorId=request.investidor.id, versaoAlgoritmo=VERSION,
                           modeloEmbeddings=encoder.model_id, recomendacoes=selected, avisos=warnings)
