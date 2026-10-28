"""Ablação exploratória dos campos: execução explícita por runpy, sem mudar produção."""
import hashlib
import importlib.metadata
import json
import platform
import runpy
from pathlib import Path
from time import perf_counter

from app.content import rank_content
from app.content_schemas import ContentRequest
from app.content_text import investor_text, sufficient
from app.embeddings import LocalEncoder, MODEL_ID


class CachedEncoder:
    model_id = MODEL_ID

    def __init__(self):
        self.encoder = LocalEncoder()
        self.cache = {}
        self.encoded_documents = 0

    def encode(self, texts):
        missing = list(dict.fromkeys(text for text in texts if text not in self.cache))
        if missing:
            vectors = self.encoder.encode(missing)
            self.cache.update(zip(missing, vectors))
            self.encoded_documents += len(missing)
        return [self.cache[text] for text in texts]


def main():
    root = Path(__file__).resolve().parent
    source = root / "evaluate_content_real.py"
    original = runpy.run_path(str(source))
    startups, investors, uid = original["STARTUPS"], original["INVESTORS"], original["uid"]
    candidates = [{"id": uid(n + 100), "descricaoPitch": pitch, "mercadoAlvo": market}
                  for n, (_, _, pitch, market) in enumerate(startups)]
    names = {s["id"]: startups[n][0] for n, s in enumerate(candidates)}
    encoder = CachedEncoder()
    report = {
        "modelo": MODEL_ID, "python": platform.python_version(),
        "versoes": {p: importlib.metadata.version(p) for p in ["sentence-transformers", "torch", "transformers"]},
        "fonte_perfis": source.name, "sha256_fonte": hashlib.sha256(source.read_bytes()).hexdigest(),
        "metodo": "A=bio; B=descricaoExperiencia; C=ambos. Mesmos textos originais, modelo CPU, preparação e rank_content de produção. Cache apenas experimental por texto exato; nenhuma seleção baseada nos resultados.",
        "delta_definicao": "cosseno da relevante MENOS cosseno da primeira; zero se relevante em primeiro, negativo caso contrário",
        "startups": [{"nome": startups[n][0], **c} for n, c in enumerate(candidates)],
        "avaliacoes": [],
    }
    started = perf_counter()
    for n, (label, bio, experience, expected) in enumerate(investors):
        for strategy in ("A", "B", "C"):
            investor = {"id": uid(n + 1), "bio": bio if strategy != "B" else None,
                        "descricaoExperiencia": experience if strategy != "A" else None}
            request = ContentRequest.model_validate({"investidor": investor, "startups": candidates, "limite": len(candidates)})
            response = rank_content(request, encoder)
            ranking = [{"nome": names[str(r.startupId)], **r.model_dump(mode="json")} for r in response.recomendacoes]
            relevant = next(r for r in ranking if r["nome"] == expected)
            first = ranking[0]
            delta = (relevant["similaridadeBruta"] - first["similaridadeBruta"]
                     if relevant["similaridadeBruta"] is not None and first["similaridadeBruta"] is not None else None)
            report["avaliacoes"].append({
                "investidor": label, "estrategia": strategy, "entrada": investor,
                "texto_preparado": investor_text(request.investidor),
                "texto_suficiente": sufficient(investor_text(request.investidor)),
                "relevante_referencia_previa": expected, "posicao_relevante": relevant["posicao"],
                "delta_relevante_primeira": delta, "ranking": ranking,
            })
    report["tempo_total_segundos_inclui_carga"] = perf_counter() - started
    report["documentos_unicos_codificados"] = encoder.encoded_documents
    report["comparativo"] = []
    for strategy in ("A", "B", "C"):
        rows = [r for r in report["avaliacoes"] if r["estrategia"] == strategy]
        report["comparativo"].append({"estrategia": strategy,
                                      "top1_referencia": sum(r["posicao_relevante"] == 1 for r in rows),
                                      "total": len(rows),
                                      "posicao_media_relevante": sum(r["posicao_relevante"] for r in rows) / len(rows)})
    destination = root / "artifacts"
    destination.mkdir(exist_ok=True)
    (destination / "content_fields_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Experimento real: influência dos campos textuais", "",
             "A: somente bio. B: somente descricaoExperiencia. C: concatenação atual.",
             "Textos originais importados de evaluate_content_real.py, sem alterações. Modelo em CPU e rank_content de produção. Cache experimental reutiliza vetores por texto exato; mesma preparação, normalização e desempate nas três estratégias.", "",
             "Referências de relevância são as definidas previamente no experimento anterior, não avaliações independentes. Delta = cosseno da relevante menos cosseno da primeira (zero quando a relevante lidera). Scores não são probabilidades.", "",
             "## Comparativo", "", "| Estratégia | Referência em primeiro | Posição média da relevante |", "| --- | ---: | ---: |"]
    for row in report["comparativo"]:
        lines.append(f"| {row['estrategia']} | {row['top1_referencia']}/{row['total']} | {row['posicao_media_relevante']:.2f} |")
    for row in report["avaliacoes"]:
        lines.extend(["", f"## {row['investidor']} — estratégia {row['estrategia']}", "",
                      f"Relevante: {row['relevante_referencia_previa']}; posição {row['posicao_relevante']}; delta {row['delta_relevante_primeira']:.6f}.", "",
                      "| Posição | Startup | Cosseno bruto | Score normalizado |", "| ---: | --- | ---: | ---: |"])
        for r in row["ranking"]:
            raw = "null" if r["similaridadeBruta"] is None else f"{r['similaridadeBruta']:.6f}"
            score = "null" if r["score"] is None else f"{r['score']:.6f}"
            lines.append(f"| {r['posicao']} | {r['nome']} | {raw} | {score} |")
        lines.extend(["", "Texto efetivamente enviado ao encoder:", "", "```text", row["texto_preparado"], "```"])
    lines.extend(["", "## Execução", "",
                  f"Documentos únicos codificados: {encoder.encoded_documents}. Modelo mantido em uma instância LocalEncoder. Tempo total com carga: {report['tempo_total_segundos_inclui_carga']:.3f} s; não é benchmark de latência da API devido ao cache experimental.", "",
                  "```powershell", "py -X utf8 -c \"import runpy; runpy.run_path('tests/evaluate_content_fields.py', run_name='__main__')\"", "```", "",
                  "As execuções sobrescrevem apenas os resultados deste experimento. O JSON registra textos, UUIDs, versões, hash da fonte e scores completos. A revisão remota do modelo não está fixada; ambiente e pequenas diferenças numéricas podem variar."])
    (destination / "content_fields_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"comparativo": report["comparativo"], "resumo": [
        {k: r[k] for k in ["investidor", "estrategia", "posicao_relevante", "delta_relevante_primeira"]}
        | {"top": r["ranking"][:2]} for r in report["avaliacoes"]],
        "documentos_unicos": encoder.encoded_documents}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
