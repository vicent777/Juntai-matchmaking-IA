"""Métricas probabilísticas, ranking condicional e diagnósticos sem ajuste em teste."""

from collections import defaultdict

import numpy as np
from sklearn.metrics import (roc_auc_score, average_precision_score, precision_recall_curve,
                             auc, precision_score, recall_score, f1_score, confusion_matrix,
                             log_loss, brier_score_loss)


def choose_threshold(y, probability):
    candidates = np.linspace(.05,.95,19)
    scores = [f1_score(y,probability>=threshold,zero_division=0) for threshold in candidates]
    return float(candidates[int(np.argmax(scores))])


def ranking(rows, indexes, scores, ks=(1,3,5,10)):
    groups=defaultdict(list)
    for i,score in zip(indexes,scores):
        row=rows[i]
        groups[row.metadados['investidor_id']].append((float(score),row.metadados['startup_id'],row.rotulo.target))
    report={}
    for k in ks:
        precision,recall=[],[]
        for candidates in groups.values():
            positives=sum(x[2] for x in candidates)
            if len(candidates)<max(k,2) or positives==0 or positives==len(candidates):
                continue
            top=sorted(candidates,key=lambda item:(-item[0],item[1]))[:k]
            hits=sum(x[2] for x in top)
            precision.append(hits/k)
            recall.append(hits/positives)
        report[str(k)]={'precision':float(np.mean(precision)) if precision else None,
                        'recall':float(np.mean(recall)) if recall else None,
                        'eligible_investors':len(precision),'all_investors':len(groups),
                        'condition':'pelo menos max(K,2) candidatas e ambas as classes; somente candidatos expostos deste teste'}
    return report


def calibration(y,probability):
    bins=[]
    ece=0.0
    for n in range(10):
        mask=(probability>=n/10)&(probability<((n+1)/10) if n<9 else probability<=1)
        if np.any(mask):
            predicted,observed=float(np.mean(probability[mask])),float(np.mean(y[mask]))
            ece+=float(np.mean(mask))*abs(predicted-observed)
            bins.append({'lower':n/10,'n':int(mask.sum()),'mean_probability':predicted,'observed_rate':observed})
    return {'ece_10':ece,'bins':bins,'method':'raw probabilities; no calibrator fitted'}


def metrics(y,scores,threshold,rows,indexes,probabilistic=True):
    y=np.asarray(y,dtype=int);scores=np.asarray(scores,dtype=float)
    if len(scores)!=len(y) or not np.all(np.isfinite(scores)) or np.any((scores<0)|(scores>1)):
        raise ValueError('Predições inválidas')
    precision,recall,_=precision_recall_curve(y,scores)
    predicted=scores>=threshold
    both=len(np.unique(y))==2
    clipped=np.clip(scores,1e-7,1-1e-7)
    return {'n':len(y),'prevalence':float(np.mean(y)),
            'roc_auc':float(roc_auc_score(y,scores)) if both else None,
            'pr_auc':float(auc(recall,precision)), 'average_precision':float(average_precision_score(y,scores)),
            'precision':float(precision_score(y,predicted,zero_division=0)),
            'recall':float(recall_score(y,predicted,zero_division=0)),
            'f1':float(f1_score(y,predicted,zero_division=0)),
            'confusion_matrix':confusion_matrix(y,predicted,labels=[0,1]).tolist(),
            'log_loss':float(log_loss(y,clipped,labels=[0,1])) if probabilistic else None,
            'brier_score':float(brier_score_loss(y,scores)) if probabilistic else None,
            'calibration':calibration(y,scores) if probabilistic else None,
            'threshold':float(threshold),'ranking':ranking(rows,indexes,scores)}


def bootstrap(y,scores,seed,repeats=200):
    rng=np.random.default_rng(seed);y=np.asarray(y);scores=np.asarray(scores)
    values={'roc_auc':[],'average_precision':[]}
    for _ in range(repeats):
        indexes=rng.integers(0,len(y),len(y))
        if len(np.unique(y[indexes]))<2:
            continue
        values['roc_auc'].append(roc_auc_score(y[indexes],scores[indexes]))
        values['average_precision'].append(average_precision_score(y[indexes],scores[indexes]))
    return {'interval_95':{key:np.quantile(value,[.025,.975]).tolist() for key,value in values.items() if value},
            'method':'bootstrap de linhas; dependência por entidade não é capturada; intervalos exploratórios'}


def subgroups(rows,indexes,scores):
    result={}
    for field in ['startup.segmento','startup.estagio']:
        groups=defaultdict(list)
        for position,index in enumerate(indexes):
            groups[rows[index].features.categoricas[field]].append(position)
        result[field]={}
        for name,positions in groups.items():
            y=np.array([rows[indexes[p]].rotulo.target for p in positions]);p=np.asarray(scores)[positions]
            if len(y)>=30 and len(np.unique(y))==2:
                result[field][name]={'n':len(y),'prevalence':float(y.mean()),'roc_auc':float(roc_auc_score(y,p)), 'average_precision':float(average_precision_score(y,p))}
    return result
