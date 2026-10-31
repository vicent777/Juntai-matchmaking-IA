"""Janelas maduras com purga de 30 dias entre blocos e holdouts por entidade."""

import hashlib
from collections import Counter
from datetime import datetime, timedelta


def temporal_split(rows):
    cutoff = datetime.fromisoformat(rows[0].metadados['data_corte'])
    window = timedelta(days=30)
    mature = [i for i, row in enumerate(rows) if datetime.fromisoformat(row.metadados['fim_janela']) <= cutoff and row.rotulo.target is not None]
    if not mature:
        raise ValueError('Sem exemplos maduros')
    start = min(datetime.fromisoformat(rows[i].metadados['t0']) for i in mature)
    end = cutoff - window
    available = end - start - 2*window
    if available.total_seconds() <= 0:
        raise ValueError('Histórico insuficiente para três janelas com purga de 30 dias')
    train_end = start + available * .70
    val_start = train_end + window
    val_end = val_start + available * .15
    test_start = val_end + window
    bounds = {'train': (start, train_end), 'validation': (val_start, val_end), 'test': (test_start, end)}
    split = {name: [i for i in mature if left <= datetime.fromisoformat(rows[i].metadados['t0']) < right] for name,(left,right) in bounds.items()}
    validate_split(rows, split)
    return split, {'boundaries': {k: [a.isoformat(), b.isoformat()] for k,(a,b) in bounds.items()},
                   'mature_total': len(mature), 'excluded_immature_or_unlabeled': len(rows)-len(mature),
                   'purged_mature': len(mature)-sum(map(len, split.values())), 'embargo_days': 30,
                   'strategy': '70/15/15 do tempo útil após reservar dois intervalos de 30 dias; não são proporções das linhas.'}


def validate_split(rows, split):
    seen = set()
    for name in ['train','validation','test']:
        indexes = split[name]
        if not indexes or len({rows[i].rotulo.target for i in indexes}) != 2:
            raise ValueError(name + ': amostra vazia ou classe única')
        for i in indexes:
            pair = (rows[i].metadados['investidor_id'],rows[i].metadados['startup_id'])
            if pair in seen:
                raise ValueError('Par compartilhado entre divisões')
            seen.add(pair)
            if rows[i].rotulo.target is None or datetime.fromisoformat(rows[i].metadados['fim_janela']) > datetime.fromisoformat(rows[i].metadados['data_corte']):
                raise ValueError('Label imaturo/indefinido')
    for left,right in [('train','validation'),('validation','test')]:
        latest = max(datetime.fromisoformat(rows[i].metadados['fim_janela']) for i in split[left])
        earliest = min(datetime.fromisoformat(rows[i].metadados['t0']) for i in split[right])
        if latest > earliest:
            raise ValueError('Vazamento pela janela de maturação')


def holdout(identifier, seed):
    return int(hashlib.sha256(f'{seed}:{identifier}'.encode()).hexdigest()[:12],16) % 5 == 0


def cold_split(rows, temporal, entity, seed):
    key = entity + '_id'
    split = {part: [i for i in indexes if holdout(rows[i].metadados[key],seed) == (part == 'test')]
             for part,indexes in temporal.items()}
    validate_split(rows,split)
    training_entities = {rows[i].metadados[key] for part in ['train','validation'] for i in split[part]}
    if training_entities & {rows[i].metadados[key] for i in split['test']}:
        raise ValueError('Entidade reservada apareceu no ajuste/validação')
    return split


def describe(rows, split):
    report = {}
    for name,indexes in split.items():
        classes=Counter(rows[i].rotulo.target for i in indexes)
        report[name]={'n':len(indexes),'negative':classes[0],'positive':classes[1],
                      'prevalence':classes[1]/len(indexes),
                      'investors':len({rows[i].metadados['investidor_id'] for i in indexes}),
                      'startups':len({rows[i].metadados['startup_id'] for i in indexes})}
    report['entity_overlap']={key:len({rows[i].metadados[key] for i in split['train']} & {rows[i].metadados[key] for i in split['test']}) for key in ['investidor_id','startup_id']}
    return report
