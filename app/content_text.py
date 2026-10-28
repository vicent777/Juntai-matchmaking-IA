"""Limpeza leve e seleção determinística de conteúdo, sem inferir preferências."""
import re
import unicodedata

from app.content_schemas import InvestidorConteudo, StartupConteudo

CANVAS_KEYS = ("problema", "solucao", "value", "customers")


def combine(values) -> str:
    seen = set()
    parts = []
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = " ".join(unicodedata.normalize("NFC", value).split())
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            parts.append(cleaned)
    return "\n".join(parts)


def investor_text(investor: InvestidorConteudo) -> str:
    return combine([investor.bio, investor.descricaoExperiencia])


def startup_text(startup: StartupConteudo) -> str:
    canvas = startup.canvasJson or {}
    return combine([startup.descricaoCurta, startup.descricaoPitch, startup.mercadoAlvo,
                    *(canvas.get(key) for key in CANVAS_KEYS)])


def sufficient(text: str) -> bool:
    # Limiar operacional conservador e explícito, não validação de qualidade.
    return len(re.findall(r"[^\W\d_]+", text, flags=re.UNICODE)) >= 3
