import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.rules import rank
from app.schemas import RulesRequest
from app.supervised.backend_export import adapt_exposure
from app.supervised import DatasetInput, build_dataset

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/matchmaking-contract.json').read_text(encoding='utf-8'))


def test_shared_node_fastapi_contract():
    assert rank(RulesRequest.model_validate(FIXTURE['request'])).model_dump(mode='json') == FIXTURE['response']
    sibling = Path(__file__).resolve().parents[2] / 'Juntai-Backend/tests/fixtures/matchmaking-contract.json'
    if sibling.exists():
        assert json.loads(sibling.read_text(encoding='utf-8')) == FIXTURE


def test_exported_snapshot_can_feed_dataset_without_database():
    exposure, snapshot = adapt_exposure(FIXTURE['stored_exposure'])
    result = build_dataset(DatasetInput(
        exposicoes=[exposure], snapshots=[snapshot], data_corte='2026-02-10T00:00:00Z',
        origem_dados='sintetica', historico_completo=True, completo_ate='2026-02-10T00:00:00Z',
    ))
    assert result.registros[0].rotulo.target == 0
    assert result.registros[0].features.derivadas['segmento.score'] == 1
    assert not result.qualidade


def test_export_mismatched_profiles_rejected():
    row = deepcopy(FIXTURE['stored_exposure'])
    row['snapshot_perfis']['investidor']['id'] = row['startup_id']
    with pytest.raises(ValueError, match='Par inconsistente'):
        adapt_exposure(row)
