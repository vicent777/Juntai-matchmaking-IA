"""Endpoint experimental: artefato real, contratos e falhas controladas."""

import copy
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.supervised.features import build_features
from app.supervised.inference.schemas import SupervisedRequest
from app.supervised.inference import service
from app.supervised.inference.service import Predictor, SupervisedUnavailable, get_predictor

FIXTURE = json.loads((Path(__file__).parent/'fixtures/matchmaking-contract.json').read_text(encoding='utf-8'))['request']


@pytest.fixture(scope='module')
def real_predictor():
    pytest.importorskip('xgboost')
    if not (service.DEFAULT_BUNDLE/'temporal/xgboost.joblib').exists():
        pytest.skip('Integração exige o bundle real level2-seed42-validated; nenhum modelo será treinado pelo teste')
    predictor=Predictor(service.DEFAULT_BUNDLE)
    predictor.load()
    return predictor


@pytest.fixture
def client(real_predictor):
    app.dependency_overrides[get_predictor]=lambda:real_predictor
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_real_single_prediction_equals_saved_pipeline(client,real_predictor):
    import joblib
    import pandas as pd
    import numpy as np
    from app.supervised.training.preparation import flatten
    payload=SupervisedRequest.model_validate(FIXTURE)
    # Arquivo já autenticado pelo loader; caminho direto só neste teste comparativo.
    direct=joblib.load(io.BytesIO((service.DEFAULT_BUNDLE/'temporal/xgboost.joblib').read_bytes()))
    frame=pd.DataFrame([flatten(build_features(payload.investidor,payload.startups[0]))])
    expected=float(direct.predict_proba(frame)[0,1])
    response=client.post('/match/supervised',json=FIXTURE)
    assert response.status_code==200
    body=response.json();row=body['recomendacoes'][0]
    assert abs(row['probabilidadeInteresse']-expected)<=1e-12
    assert row['startupId']==FIXTURE['startups'][0]['id'] and row['posicao']==1
    assert body['experimental'] and body['origemTreinamento']=='sintetica'
    assert row['versaoFeatures']=='profiles-rules-v1' and body['versaoTarget']=='first-interest-v1'
    assert 'score' not in row and row['avisos']


def multi_payload():
    payload=copy.deepcopy(FIXTURE)
    second=copy.deepcopy(payload['startups'][0]);second['id']='33333333-3333-4333-8333-333333333333'
    second.update(segmento='fintech',estagio='escala',capitalProcurado='50000.00',numeroClientes=120)
    payload['startups'].append(second)
    return payload


def test_real_multiple_probabilities_sort_and_limit(client):
    payload=multi_payload()
    first=client.post('/match/supervised',json=payload).json()
    payload['startups'].reverse()
    assert client.post('/match/supervised',json=payload).json()==first
    scores=[r['probabilidadeInteresse'] for r in first['recomendacoes']]
    assert scores==sorted(scores,reverse=True) and all(0<=p<=1 for p in scores)
    payload['limite']=1
    assert client.post('/match/supervised',json=payload).json()['recomendacoes']==first['recomendacoes'][:1]


def test_real_ties_are_by_uuid_and_ids_do_not_predict(client):
    payload=copy.deepcopy(FIXTURE)
    duplicate=copy.deepcopy(payload['startups'][0]);duplicate['id']='11111111-1111-4111-8111-111111111112'
    payload['startups'].append(duplicate)
    rows=client.post('/match/supervised',json=payload).json()['recomendacoes']
    assert rows[0]['probabilidadeInteresse']==rows[1]['probabilidadeInteresse']
    assert [r['startupId'] for r in rows]==sorted(s['id'] for s in payload['startups'])
    changed=copy.deepcopy(payload);changed['investidor']['id']='99999999-9999-4999-8999-999999999999'
    assert [r['probabilidadeInteresse'] for r in client.post('/match/supervised',json=changed).json()['recomendacoes']]==[r['probabilidadeInteresse'] for r in rows]


def test_real_incomplete_profiles_preserve_missing_treatment(client):
    payload={'investidor':{'id':FIXTURE['investidor']['id']},'startups':[{'id':FIXTURE['startups'][0]['id']}]}
    response=client.post('/match/supervised',json=payload)
    assert response.status_code==200
    row=response.json()['recomendacoes'][0]
    assert any('incompleto' in warning for warning in row['avisos'])
    assert any('indeterminada' in warning for warning in row['avisos'])
    payload['investidor']['ticketMaximo']=None
    assert client.post('/match/supervised',json=payload).json()==response.json()


@pytest.mark.parametrize('mutation',[
    lambda p:p.update(startups=[]),
    lambda p:p['startups'].append(copy.deepcopy(p['startups'][0])),
    lambda p:p['investidor'].update(id='invalid'),
    lambda p:p['investidor'].update(ticketMinimo='100',ticketMaximo='1'),
    lambda p:p['startups'][0].update(segmento='invalid'),
    lambda p:p.update(limite=True),
    lambda p:p['startups'][0].update(numeroClientes=-1),
    lambda p:p.update(model_path='untrusted.joblib'),
    lambda p:p['investidor'].update(target=1),
    lambda p:p['startups'][0].update(ocorrido_em='2026-01-01T00:00:00Z'),
])
def test_invalid_input_is_422_without_loading_model(mutation):
    payload=copy.deepcopy(FIXTURE);mutation(payload)
    with patch.object(Predictor,'load',side_effect=AssertionError('não carregar modelo')):
        assert TestClient(app).post('/match/supervised',json=payload).status_code==422


def test_real_ineligible_profiles_are_excluded(client):
    payload=multi_payload();payload['startups'][0]['usuario']['ativo']=False
    payload['startups'][1]['statusModeracao']='pendente'
    body=client.post('/match/supervised',json=payload).json()
    assert body['recomendacoes']==[] and len(body['excluidas'])==2


def test_missing_model_returns_sanitized_503():
    app.dependency_overrides[get_predictor]=lambda:Predictor(service.ARTIFACTS/'nonexistent-bundle')
    try:
        response=TestClient(app).post('/match/supervised',json=FIXTURE)
        assert response.status_code==503
        assert response.json()=={'detail':'Modelo supervisionado indisponível ou incompatível.'}
        assert 'nonexistent' not in response.text
    finally:app.dependency_overrides.clear()


@pytest.fixture
def copied_bundle(real_predictor,tmp_path,monkeypatch):
    trusted=json.loads(service.REGISTRY.read_text(encoding='utf-8'))
    for relative in trusted['files']:
        destination=tmp_path/'bundle'/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes((service.DEFAULT_BUNDLE/relative).read_bytes())
    monkeypatch.setattr(service,'ARTIFACTS',tmp_path)
    return tmp_path/'bundle'


def test_tampered_pickle_is_never_deserialized(copied_bundle):
    path=copied_bundle/'temporal/xgboost.joblib';path.write_bytes(b'untrusted-pickle')
    with patch('joblib.load',side_effect=AssertionError('não desserializar')) as loader:
        with pytest.raises(SupervisedUnavailable):Predictor(copied_bundle).load()
        loader.assert_not_called()


def test_replacing_bundle_manifest_does_not_grant_trust(copied_bundle):
    path=copied_bundle/'manifest.json';path.write_text('{}',encoding='utf-8')
    with patch('joblib.load') as loader:
        with pytest.raises(SupervisedUnavailable):Predictor(copied_bundle).load()
        loader.assert_not_called()


def test_runtime_dependency_mismatch_rejected_before_unpickle(copied_bundle,monkeypatch):
    monkeypatch.setattr(service.importlib.metadata,'version',lambda name:'0.0.0')
    with patch('joblib.load') as loader:
        with pytest.raises(SupervisedUnavailable):Predictor(copied_bundle).load()
        loader.assert_not_called()


def test_feature_order_incompatible_artifact_rejected(copied_bundle):
    import joblib
    original=joblib.load(io.BytesIO((copied_bundle/'temporal/xgboost.joblib').read_bytes()))
    original.named_steps['preprocess'].selected_=list(reversed(original.named_steps['preprocess'].selected_))
    with patch('joblib.load',return_value=original):
        with pytest.raises(SupervisedUnavailable):Predictor(copied_bundle).load()


def test_invalid_predictions_fail_without_fabricated_probability(real_predictor):
    pipeline,trusted=real_predictor.load()
    import numpy as np
    for prediction in [np.array([[.2,np.nan]]),np.array([[.2,1.2]]),np.array([[.2,.2]]),np.array([[.1,.8,.1]])]:
        with patch.object(pipeline,'predict_proba',return_value=prediction):
            with pytest.raises(SupervisedUnavailable):real_predictor.rank(SupervisedRequest.model_validate(FIXTURE))


def test_lazy_loading_is_cached_and_thread_safe(copied_bundle):
    import joblib
    predictor=Predictor(copied_bundle)
    assert predictor._loaded is None
    with patch('joblib.load',wraps=joblib.load) as loader:
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:predictor.load(),range(4)))
        assert loader.call_count==1
        assert all(value is results[0] for value in results)


def test_real_comparison_with_1a_keeps_scores_separate(client):
    payload=multi_payload()
    supervised=client.post('/match/supervised',json=payload).json()
    # /match/rules exige somente os campos mínimos do Nível 1A.
    rules_payload=copy.deepcopy(payload)
    for startup in rules_payload['startups']:
        for key in ['capitalProcurado','numeroClientes']:startup.pop(key,None)
    rules=client.post('/match/rules',json=rules_payload).json()
    assert {r['startupId'] for r in rules['recomendacoes']}=={r['startupId'] for r in supervised['recomendacoes']}
    assert all('score' in r and 'probabilidadeInteresse' not in r for r in rules['recomendacoes'])
    assert all('probabilidadeInteresse' in r and 'score' not in r for r in supervised['recomendacoes'])
    assert client.post('/match/supervised',json=payload).json()==supervised


def test_openapi_and_swagger_expose_new_endpoint():
    client=TestClient(app)
    assert '/match/supervised' in client.get('/openapi.json').json()['paths']
    assert client.get('/docs').status_code==200
