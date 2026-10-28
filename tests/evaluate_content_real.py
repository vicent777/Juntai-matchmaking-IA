"""Avaliação exploratória explícita: execute por runpy a partir da raiz.
Nenhum perfil é usado operacionalmente; não é coletado pelo pytest.
"""
import importlib.metadata
import json
import os
import platform
from pathlib import Path
from statistics import median
from time import perf_counter
from unittest.mock import patch
from uuid import UUID

from app.content import rank_content
from app.content_schemas import ContentRequest
from app.embeddings import LocalEncoder, load_model, MODEL_ID


def uid(number):
    return str(UUID(int=number, version=4))


# Fixados antes da execução: não adaptar estes exemplos aos resultados.
STARTUPS = [
    ("CampoConecta", "agricultura", "Conectamos pequenos lavradores a compradores de alimentos, reduzindo intermediários e perdas na colheita.", "Cooperativas rurais e feirantes"),
    ("CuidadoPerto", "saúde", "Acompanhamento remoto de pessoas com diabetes e hipertensão. A equipe assistencial recebe alertas e organiza o cuidado fora do hospital.", "Clínicas e operadoras de planos médicos"),
    ("AprenderJuntos", "educação", "Professores identificam dificuldades de leitura e matemática e adaptam atividades à evolução de cada aluno.", "Escolas de ensino fundamental"),
    ("CaixaSimples", "finanças", "Microempreendedores controlam entradas, despesas e cobranças e conseguem antecipar recebíveis para manter o capital de giro.", "Pequenos comércios e prestadores de serviços"),
    ("OrbitaGames", "jogos", "Criamos aventuras de exploração espacial para consoles, com partidas cooperativas e venda de itens cosméticos.", "Pessoas que jogam videogame"),
    ("SolLocal", "energia", "Instalamos geração fotovoltaica compartilhada para reduzir a conta de luz de pequenos negócios sem exigir painéis no imóvel.", "Comércios de bairro e pequenas empresas"),
    ("PerfilVazio", "controle ausente", None, None),
]
INVESTORS = [
    ("Agro", "Quero apoiar soluções que aproximem produtores familiares do consumidor e melhorem a comercialização no campo.", "Atuei na distribuição de produtos agrícolas e na organização de cooperativas.", "CampoConecta"),
    ("Saúde", "Busco negócios que previnam complicações de doenças crônicas e ampliem o acesso ao atendimento, especialmente longe dos grandes centros.", "Trabalhei com gestão de hospitais e serviços de telemedicina.", "CuidadoPerto"),
    ("Educação", "Procuro ferramentas que ajudem crianças a aprender melhor, respeitando ritmos diferentes e apoiando o trabalho docente.", "Tenho experiência em formação de educadores e avaliação pedagógica.", "AprenderJuntos"),
    ("Mudança de setor", "Hoje quero investir em prevenção de doenças e cuidado de pacientes em casa.", "Passei vinte anos em bancos, desenvolvendo crédito, pagamentos, conciliação financeira, antecipação de recebíveis e análise de risco para microempresas. Liderei produtos de capital de giro e serviços financeiros digitais para pequenos comerciantes.", "CuidadoPerto"),
]


def main():
    started = perf_counter()
    model = load_model()
    load_seconds = perf_counter() - started
    import torch

    candidates = [{"id": uid(n + 100), "descricaoPitch": pitch, "mercadoAlvo": market}
                  for n, (_, _, pitch, market) in enumerate(STARTUPS)]
    names = {s["id"]: STARTUPS[n][0] for n, s in enumerate(candidates)}
    report = {
        "modelo": MODEL_ID, "device": str(model.device), "python": platform.python_version(),
        "cpu": platform.processor(), "logical_cpus": os.cpu_count(), "torch_threads": torch.get_num_threads(),
        "versoes": {p: importlib.metadata.version(p) for p in ["sentence-transformers", "torch", "transformers", "huggingface-hub"]},
        "carga_modelo_cache_segundos": load_seconds,
        "metodo": "Carga em processo novo, após download pelo teste opcional. Inferência inclui preparação, tokenização, embeddings de todos os perfis e ranking; sem HTTP. Três repetições após primeira inferência; sem cache de embeddings.",
        "startups": [{"nome": name, "setor_referencia": sector, **candidates[n]} for n, (name, sector, _, _) in enumerate(STARTUPS)],
        "avaliacoes": [],
    }
    encoder = LocalEncoder()
    with patch("app.embeddings.load_model", return_value=model) as loader:
        for n, (label, bio, experience, expected) in enumerate(INVESTORS):
            request = ContentRequest.model_validate({"investidor": {"id": uid(n + 1), "bio": bio, "descricaoExperiencia": experience}, "startups": candidates, "limite": len(candidates)})
            started = perf_counter()
            response = rank_content(request, encoder)
            first = perf_counter() - started
            durations = []
            for _ in range(3):
                started = perf_counter()
                repeated = rank_content(request, encoder)
                durations.append(perf_counter() - started)
                assert [r.startupId for r in repeated.recomendacoes] == [r.startupId for r in response.recomendacoes]
            report["avaliacoes"].append({
                "investidor": label, "entrada": request.investidor.model_dump(mode="json"),
                "referencia_humana_top1_previa": expected,
                "primeira_inferencia_segundos": first, "repeticoes_segundos": durations,
                "mediana_inferencia_segundos": median(durations),
                "ranking": [{"nome": names[str(r.startupId)], **r.model_dump(mode="json")} for r in response.recomendacoes],
            })
        report["chamadas_loader_no_encoder"] = loader.call_count
    destination = Path(__file__).parent / "artifacts" / "content_real_results.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
