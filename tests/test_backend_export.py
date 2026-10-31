import json
from copy import deepcopy
from pathlib import Path
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.rules import rank
from app.schemas import RulesRequest
from app.supervised.backend_export import StoredExposure, adapt_exposure
from app.supervised import DatasetInput, build_dataset

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/matchmaking-contract.json').read_text(encoding='utf-8'))
SUPERVISED = json.loads((Path(__file__).parent / 'fixtures/stored-supervised-exposure.json').read_text(encoding='utf-8'))


def exported_dataset(row, events=(), cutoff_days=40, complete=True):
    exposure, snapshot = adapt_exposure(row)
    cutoff = exposure.ocorrido_em + timedelta(days=cutoff_days)
    return build_dataset(DatasetInput(
        exposicoes=[exposure], snapshots=[snapshot], interacoes=list(events), data_corte=cutoff,
        origem_dados=StoredExposure.model_validate(row).origem_dados, historico_completo=complete,
        completo_ate=cutoff if complete else None,
    ))


def interest(day=5):
    return dict(id='synthetic-interest', investidor_id=SUPERVISED['investidor_id'], startup_id=SUPERVISED['startup_id'],
                ocorrido_em=datetime.fromisoformat(SUPERVISED['ocorrido_em'].replace('Z','+00:00'))+timedelta(days=day),
                tipo_evento='interesse_demonstrado', metadados={'probabilidadeInteresse':.99,'future_revenue':999999})


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


@pytest.mark.parametrize('origin', ['discovery', 'rules', 'supervised'])
def test_all_origins_preserve_metadata_outside_features(origin):
    row=deepcopy(SUPERVISED);row['origem_recomendacao']=origin
    if origin=='discovery':row.update(posicao_ranking=None,versao_recomendador=None)
    elif origin=='rules':row['versao_recomendador']='1a-v3'
    exposure,snapshot=adapt_exposure(row)
    assert exposure.origem_recomendacao==origin
    result=exported_dataset(row).registros[0]
    assert result.auditoria['origem_recomendacao']==origin
    assert result.auditoria['versao_recomendador']==row['versao_recomendador']
    assert result.auditoria['posicao_ranking']==row['posicao_ranking']
    keys={key for group in result.features.model_dump().values() for key in group}
    assert not {'posicao_ranking','versao_recomendador','probabilidadeInteresse','target','ocorrido_em'} & keys


def test_supervised_end_to_end_matches_persisted_snapshot_features_and_target():
    result=exported_dataset(SUPERVISED,[interest()])
    row=result.registros[0]
    assert row.rotulo.target==1 and not result.qualidade
    assert row.auditoria['versao_recomendador']=='xgboost-level2-seed42-temporal-v1'
    assert row.features.categoricas['investidor.estado']=='PE'
    assert row.features.categoricas['startup.estado']=='PE'
    assert row.features.numericas['startup.capitalProcurado']==100000
    assert row.features.numericas['investidor.ticketMaximo']==50000
    assert row.features.derivadas['capital_por_ticket_maximo']==2
    assert row.features.derivadas['segmento.score']==1
    assert row.auditoria['snapshot_estado_em']==row.metadados['t0']
    assert row.metadados['origem_dados']=='sintetica'
    # Fixture contém exatamente as chaves permitidas na projeção Node atual.
    assert 'usuario' not in SUPERVISED['snapshot_perfis']['investidor']
    assert 'probabilidadeInteresse' not in SUPERVISED['snapshot_perfis']['startup']


@pytest.mark.parametrize('origin',['rules','discovery'])
def test_legacy_snapshot_and_optional_ranking_metadata_remain_valid(origin):
    row=deepcopy(FIXTURE['stored_exposure']);row.update(origem_recomendacao=origin,posicao_ranking=None,versao_recomendador=None)
    result=exported_dataset(row).registros[0]
    assert result.features.categoricas['investidor.estado'] is None
    assert result.features.categoricas['startup.estado'] is None
    assert result.features.ausentes['startup.estado']
    assert result.rotulo.target==0


def test_behavior_and_model_metadata_never_change_features():
    baseline=exported_dataset(SUPERVISED).registros[0]
    changed=deepcopy(SUPERVISED);changed.update(posicao_ranking=99,versao_recomendador='other-experimental-version')
    positive=exported_dataset(changed,[interest()]).registros[0]
    assert baseline.features==positive.features
    assert baseline.rotulo.target==0 and positive.rotulo.target==1
    assert baseline.auditoria!=positive.auditoria


@pytest.mark.parametrize('events,days,complete,target,status',[
    ([],40,True,0,'negativo'),([interest(30)],30,True,1,'positivo'),
    ([interest(31)],40,True,0,'negativo'),([],10,True,None,'censurado'),
    ([interest()],40,False,None,'historico_incompleto'),([interest(45)],40,True,0,'negativo'),
    ([interest(0)],40,True,None,'interesse_previo'),
])
def test_export_preserves_existing_30_day_label_logic(events,days,complete,target,status):
    result=exported_dataset(SUPERVISED,events,days,complete)
    assert result.registros[0].rotulo.target==target
    assert result.registros[0].rotulo.status_rotulo==status
    if events and days==40 and events[0]['ocorrido_em']>datetime.fromisoformat(result.registros[0].metadados['data_corte']):
        assert result.registros[0].auditoria['eventos_ids']==[]
        assert 'evento_futuro' in {issue.codigo for issue in result.qualidade}


@pytest.mark.parametrize('path,value',[
    (('probabilidadeInteresse',),.99),
    (('snapshot_perfis','startup','probabilidadeInteresse'),.99),
    (('snapshot_perfis','investidor','target'),1),
    (('snapshot_perfis','startup','ocorrido_em'),'2026-01-02T00:00:00Z'),
    (('snapshot_perfis','startup','numeroClientes'),-1),
    (('snapshot_perfis','investidor','estado'),'INVALID'),
    (('origem_recomendacao',),'unknown'),(('posicao_ranking',),0),
    (('posicao_ranking',),True),(('posicao_ranking',),'2'),
    (('posicao_ranking',),None),(('versao_recomendador',),None),
    (('versao_recomendador',),' '),(('versao_recomendador',),'v'*101),
    (('ocorrido_em',),'2026-01-01T12:00:00'),
])
def test_invalid_or_leaking_export_is_rejected(path,value):
    row=deepcopy(SUPERVISED);node=row
    for key in path[:-1]:node=node[key]
    node[path[-1]]=value
    with pytest.raises(ValidationError):adapt_exposure(row)


def test_supervised_missing_profile_data_is_preserved_and_reproducible():
    row=deepcopy(SUPERVISED)
    row['snapshot_perfis']={'investidor':{'id':row['investidor_id']},'startup':{'id':row['startup_id']}}
    a=exported_dataset(row);b=exported_dataset(row)
    assert a.model_dump_json()==b.model_dump_json()
    assert a.registros[0].features.numericas['startup.capitalProcurado'] is None
    assert a.registros[0].features.categoricas['startup.estado'] is None
    assert a.registros[0].features.ausentes['startup.capitalProcurado']
