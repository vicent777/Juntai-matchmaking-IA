"""Contratos, separação temporal e transformações ajustadas só no treino."""

from datetime import datetime,timedelta,timezone
from types import SimpleNamespace

import joblib
import numpy as np
import pandas as pd
import pytest

pytest.importorskip('sklearn')

from app.supervised.training.preparation import flatten,TEMPLATE,Preprocessor
from app.supervised.training.splitting import temporal_split,validate_split,cold_split,holdout
from app.supervised.training.evaluation import metrics,ranking,choose_threshold,calibration
from app.supervised.training.experiment import models


def example(day,label,investor='i',startup=None):
    t0=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=day)
    return SimpleNamespace(metadados={'t0':t0.isoformat(),'fim_janela':(t0+timedelta(days=30)).isoformat(),
                                     'data_corte':datetime(2026,6,1,tzinfo=timezone.utc).isoformat(),
                                     'investidor_id':investor,'startup_id':startup or str(day)},rotulo=SimpleNamespace(target=label))


def test_temporal_purges_all_classes_and_never_splits_pair():
    rows=[example(day,day%2,'i'+str(day%5)) for day in range(151)]
    split,audit=temporal_split(rows)
    validate_split(rows,split)
    assert audit['purged_mature']>=60
    assert audit['excluded_immature_or_unlabeled']>=29
    used=[i for part in split.values() for i in part]
    assert len(used)==len(set(used))
    for a,b in [('train','validation'),('validation','test')]:
        assert max(rows[i].metadados['fim_janela'] for i in split[a])<=min(rows[i].metadados['t0'] for i in split[b])


def test_early_positive_is_excluded_until_full_maturity():
    rows=[example(day,day%2) for day in range(150)]
    rows[-1].rotulo.target=1
    split,_=temporal_split(rows)
    assert 149 not in [i for part in split.values() for i in part]


def test_overlapping_windows_duplicate_pairs_and_single_classes_rejected():
    rows=[example(day,day%2) for day in range(120)]
    with pytest.raises(ValueError,match='maturação'):
        validate_split(rows,{'train':[0,1],'validation':[10,11],'test':[80,81]})
    rows[40].metadados['startup_id']=rows[0].metadados['startup_id']
    with pytest.raises(ValueError,match='Par'):
        validate_split(rows,{'train':[0,1],'validation':[40,41],'test':[80,81]})


def test_insufficient_history_is_explicit():
    rows=[example(day,day%2) for day in range(31)]
    for r in rows:r.metadados['data_corte']='2026-03-01T00:00:00+00:00'
    with pytest.raises(ValueError,match='insuficiente'):
        temporal_split(rows)


def test_cold_entities_absent_from_fitting_and_validation():
    warm=next('i'+str(i) for i in range(100) if not holdout('i'+str(i),42))
    cold=next('i'+str(i) for i in range(100) if holdout('i'+str(i),42))
    rows=[example(day,day%2,investor=cold if day%4<2 else warm) for day in range(151)]
    temporal,_=temporal_split(rows)
    split=cold_split(rows,temporal,'investidor',42)
    assert all(rows[i].metadados['investidor_id']==warm for p in ['train','validation'] for i in split[p])
    assert all(rows[i].metadados['investidor_id']==cold for i in split['test'])


def test_allowlist_excludes_city_and_rejects_future_fields():
    import copy
    features=copy.deepcopy(TEMPLATE)
    flat=flatten(features)
    assert len(flat)==110
    assert not any(c.endswith('.cidade') for c in flat)
    features['numericas']['target']=1
    with pytest.raises(ValueError,match='permitida'):
        flatten(features)


def test_preprocessor_vocabulary_statistics_and_selection_are_train_only(tmp_path):
    train=pd.DataFrame({'numericas::money':[1.,3.,np.nan], 'categoricas::segment':['agtech','fintech','agtech'],
                        'multivaloradas::needs':[('a',),('b',),('a',)], 'ausentes::constant':[0.,0.,0.],
                        'numericas::duplicate':[1.,3.,np.nan]})
    processor=Preprocessor().fit(train)
    before=processor.get_feature_names_out().tolist()
    test=train.iloc[:1].copy();test['numericas::money']=1e12;test['categoricas::segment']='FUTURE';test['multivaloradas::needs']=[('NEW',)]
    transformed=processor.transform(test)
    assert transformed.shape[1]==len(before)
    assert not any('FUTURE' in n or 'NEW' in n for n in before)
    assert processor.constant_==['ausentes::constant']
    assert processor.duplicates_=={'numericas::duplicate':'numericas::money'}
    assert processor.transformer_.named_transformers_['numeric'].named_steps['impute'].statistics_[0]==2
    path=tmp_path/'processor.joblib';joblib.dump(processor,path)
    np.testing.assert_array_equal(joblib.load(path).transform(test).toarray(),transformed.toarray())


def test_metrics_calibration_and_ranking_known_values():
    rows=[example(i,i%2,'same') for i in range(4)]
    y=np.array([0,1,0,1]);p=np.array([.1,.9,.2,.8])
    result=metrics(y,p,.5,rows,list(range(4)))
    assert result['roc_auc']==1 and result['average_precision']==1
    assert result['confusion_matrix']==[[2,0],[0,2]]
    assert result['ranking']['1']['precision']==1
    assert result['ranking']['5']['precision'] is None
    assert sum(b['n'] for b in result['calibration']['bins'])==4
    raw=metrics(y,p,.5,rows,list(range(4)),False)
    assert raw['log_loss'] is None and raw['brier_score'] is None
    assert .05<=choose_threshold(y,p)<=.95


def test_ranking_requires_candidates_and_positives_and_rejects_bad_probabilities():
    rows=[example(i,0,'same') for i in range(4)]
    assert ranking(rows,list(range(4)),[.1,.2,.3,.4])['1']['eligible_investors']==0
    trivial=[example(0,1,'one'),example(1,1,'all-positive'),example(2,1,'all-positive')]
    assert ranking(trivial,[0,1,2],[.5,.4,.3])['1']['eligible_investors']==0
    with pytest.raises(ValueError):metrics([0,1],[.1,2],.5,rows,[0,1])


def test_models_are_seeded_and_complexity_limited():
    configured=models(123)
    assert set(configured)=={'logistic_regression','random_forest','xgboost'}
    assert all(m.get_params()['random_state']==123 for m in configured.values())
    assert configured['random_forest'].max_depth==8
    assert configured['xgboost'].get_params()['early_stopping_rounds']==30
