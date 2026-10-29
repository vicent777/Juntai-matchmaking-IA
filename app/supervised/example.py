"""Exemplo exclusivamente sintético: python -m app.supervised.example."""

from app.supervised import DatasetInput, build_dataset


def synthetic_example():
    investor_id = "11111111-1111-4111-8111-111111111111"
    startup_ids = ["22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333"]
    investor = {"id": investor_id, "tipoInvestidor": "anjo_mentor", "ticketMaximo": "1000.00",
                "segmentosInteresse": ["agtech"]}
    exposures, snapshots = [], []
    for index, startup_id in enumerate(startup_ids):
        exposure_id = f"exemplo-{index + 1}"
        exposures.append({"exposicao_id": exposure_id, "investidor_id": investor_id,
                          "startup_id": startup_id, "ocorrido_em": "2026-01-01T00:00:00Z"})
        snapshots.append({"exposicao_id": exposure_id, "estado_em": "2026-01-01T00:00:00Z",
                          "historico_confirmado": True, "investidor": investor,
                          "startup": {"id": startup_id, "segmento": "agtech" if index == 0 else "fintech",
                                      "capitalProcurado": "5000.00"}})
    return build_dataset(DatasetInput.model_validate({
        "origem_dados": "sintetica", "data_corte": "2026-02-10T00:00:00Z",
        "historico_completo": True, "completo_ate": "2026-02-10T00:00:00Z",
        "exposicoes": exposures, "snapshots": snapshots,
        "interacoes": [{"id": "interesse-1", "investidor_id": investor_id, "startup_id": startup_ids[0],
                        "tipo_evento": "interesse_demonstrado", "ocorrido_em": "2026-01-06T00:00:00Z"}],
    }))


if __name__ == "__main__":
    print(synthetic_example().model_dump_json(indent=2))
