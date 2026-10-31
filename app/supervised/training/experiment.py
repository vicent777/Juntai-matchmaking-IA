"""Treinamento, serialização e diagnósticos isolados de qualquer serviço."""

import importlib.metadata
import json
import platform
import math
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from app.rules import rank
from app.schemas import RulesRequest
from app.supervised.synthetic.export import write_json, file_hash
from app.supervised.training.preparation import Preprocessor, load_dataset
from app.supervised.training.splitting import temporal_split,cold_split,describe
from app.supervised.training.evaluation import choose_threshold,metrics,bootstrap,subgroups


def models(seed):
    return {
        'logistic_regression':LogisticRegression(C=1,max_iter=1500,random_state=seed),
        'random_forest':RandomForestClassifier(n_estimators=250,max_depth=8,min_samples_leaf=8,max_features=.7,n_jobs=2,random_state=seed),
        'xgboost':XGBClassifier(n_estimators=500,max_depth=3,learning_rate=.05,min_child_weight=8,
                                subsample=.85,colsample_bytree=.85,reg_lambda=5,
                                objective='binary:logistic',eval_metric='logloss',
                                early_stopping_rounds=30,n_jobs=2,random_state=seed,tree_method='hist'),
    }


def feature_importance(model,names):
    values=model.coef_[0] if hasattr(model,'coef_') else model.feature_importances_
    order=np.argsort(-np.abs(values))[:25]
    return [{'feature':str(names[i]),'value':float(values[i])} for i in order]


def score_rules(data,indexes):
    scores=[]
    for index in indexes:
        snapshot=data.snapshots[data.rows[index].metadados['exposicao_id']]
        score=rank(RulesRequest(investidor=snapshot.investidor,startups=[snapshot.startup],limite=1)).recomendacoes[0].score
        if score is None:
            raise ValueError('1A sem score em exemplo avaliado; definir política explícita antes de comparar')
        scores.append(score)
    return np.array(scores)


def run_scenario(data,split,directory,seed):
    directory.mkdir()
    X={key:data.frame.iloc[indexes] for key,indexes in split.items()}
    y={key:np.array([data.rows[i].rotulo.target for i in indexes],dtype=int) for key,indexes in split.items()}
    processor=Preprocessor().fit(X['train'])
    encoded={key:processor.transform(value) for key,value in X.items()}
    names=processor.get_feature_names_out()
    report={'split':describe(data.rows,split), 'preprocessing':{'selected_columns':processor.selected_,
             'constants_removed':processor.constant_,'exact_duplicates_removed':processor.duplicates_,
             'encoded_features':len(names),'fit_rows':len(y['train'])},'models':{}}
    write_json(directory/'split.json',{key:[data.rows[i].metadados['exposicao_id'] for i in indexes] for key,indexes in split.items()})
    estimators=models(seed)
    prevalence=float(y['train'].mean())
    for name,model in estimators.items():
        if name=='xgboost':
            model.fit(encoded['train'],y['train'],eval_set=[(encoded['validation'],y['validation'])],verbose=False)
        else:
            model.fit(encoded['train'],y['train'])
        probabilities={key:model.predict_proba(values)[:,1] for key,values in encoded.items()}
        threshold=choose_threshold(y['validation'],probabilities['validation'])
        entry={'parameters':{k:('NaN' if isinstance(v,float) and not math.isfinite(v) else v) for k,v in model.get_params().items()}, 'threshold_method':'max F1 over fixed 19-point grid on validation only',
               'partitions':{key:metrics(y[key],probabilities[key],threshold,data.rows,split[key]) for key in split},
               'test_uncertainty':bootstrap(y['test'],probabilities['test'],seed),
               'subgroups':subgroups(data.rows,split['test'],probabilities['test']),
               'importance':feature_importance(model,names)}
        if name=='xgboost':entry['best_iteration']=int(model.best_iteration)
        missing=np.array([any(data.rows[i].features.ausentes.values()) for i in split['test']])
        entry['missingness_groups']={}
        for label,mask in [('has_missing',missing),('no_missing',~missing)]:
            if mask.sum() and len(np.unique(y['test'][mask]))==2:
                entry['missingness_groups'][label]=metrics(y['test'][mask],probabilities['test'][mask],threshold,data.rows,[i for i,m in zip(split['test'],mask) if m])
        masked=X['test'].copy(deep=True)
        numeric=[c for c in masked if c.startswith('numericas::')]
        for column in numeric:
            masked[column]=np.nan
            indicator='ausentes::'+column.split('::',1)[1]
            if indicator in masked:masked[indicator]=1.
        masked['derivadas::capital_por_ticket_maximo']=np.nan
        masked['ausentes::capital_por_ticket_maximo']=1.
        # Cenário artificial de robustez; os demais atributos de snapshot são preservados.
        stress=model.predict_proba(processor.transform(masked))[:,1]
        entry['missing_numeric_stress']=metrics(y['test'],stress,threshold,data.rows,split['test'])
        entry['train_test_gap_roc_auc']=entry['partitions']['train']['roc_auc']-entry['partitions']['test']['roc_auc']
        pipeline=Pipeline([('preprocess',processor),('classifier',model)])
        model_path=directory/(name+'.joblib')
        joblib.dump(pipeline,model_path)
        restored=joblib.load(model_path)
        if not np.allclose(restored.predict_proba(X['test'])[:,1],probabilities['test'],rtol=0,atol=1e-12):
            raise ValueError('Predições mudaram após serialização')
        if name=='xgboost':model.save_model(directory/'xgboost.ubj')
        with (directory/(name+'-predictions.jsonl')).open('w',encoding='utf-8') as stream:
            for index,probability in zip(split['test'],probabilities['test']):
                row=data.rows[index]
                stream.write(json.dumps({'exposure_id':row.metadados['exposicao_id'],'target':row.rotulo.target,'probability':float(probability)})+'\n')
        entry['serialization_verified']=True
        report['models'][name]=entry
    constants={key:np.full(len(values),prevalence) for key,values in y.items()}
    rules={key:score_rules(data,indexes) for key,indexes in split.items()}
    report['baselines']={}
    for name,scores,probabilistic in [('prevalence',constants,True),('level1a',rules,False)]:
        threshold=choose_threshold(y['validation'],scores['validation'])
        report['baselines'][name]={'partitions':{key:metrics(y[key],scores[key],threshold,data.rows,split[key],probabilistic) for key in split},
                                  'interpretation':'probabilidade constante ajustada no treino' if probabilistic else 'score 1A original não calibrado; log loss/Brier/calibração não se aplicam'}
    # Seleção exploratória somente na validação; o teste não define modelo/limiar.
    report['validation_best_ap']=max(report['models'],key=lambda name:report['models'][name]['partitions']['validation']['average_precision'])
    write_json(directory/'metrics.json',report)
    return report


def run(data_directory:Path,output:Path,seed:int):
    if output.exists():raise FileExistsError('Escolha um diretório novo; artefatos existentes são preservados')
    data=load_dataset(data_directory)
    split,temporal_audit=temporal_split(data.rows)
    output.mkdir(parents=True)
    report={'seed':seed,'environment':{'python':platform.python_version(),**{p:importlib.metadata.version(p) for p in ['numpy','pandas','scikit-learn','xgboost','scipy','joblib']}},
            'data_audit':data.audit,'temporal_audit':temporal_audit,'scenarios':{},
            'limitations':['Comportamento e cronologia sintéticos; snapshots não são reconstruções históricas.',
                           'Intervalos de maturação reduzem fortemente a amostra; uma única divisão temporal.',
                           'Avaliação principal permite entidades repetidas; IDs/cidades não entram como features.',
                           'Ranking avalia apenas candidatos expostos rotulados; poucos investidores têm K candidatos e positivos.',
                           'Probabilidades não foram recalibradas; validação escolhe limiar e early stopping.',
                           'Modelo definitivo não escolhido; nenhuma integração, endpoint ou deploy.']}
    report['scenarios']['temporal']=run_scenario(data,split,output/'temporal',seed)
    for entity in ['investidor','startup']:
        name='unseen_'+entity
        try:
            held=cold_split(data.rows,split,entity,seed)
        except ValueError as error:
            report['scenarios'][name]={'not_applicable':str(error)}
            continue
        report['scenarios'][name]=run_scenario(data,held,output/name,seed)
    write_json(output/'metrics.json',report)
    hashes={str(path.relative_to(output)).replace('\\','/'):file_hash(path) for path in sorted(output.rglob('*')) if path.is_file()}
    write_json(output/'manifest.json',{'sha256':hashes,'data_manifest_sha256':data.audit['manifest_sha256']})
    return report
