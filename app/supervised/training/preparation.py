"""Auditoria do contrato e seleção de informação disponível antes da exposição."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction import DictVectorizer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.supervised.dataset import build_dataset, CONTRACT_VERSION, FEATURE_VERSION, TARGET_VERSION
from app.supervised.features import build_features
from app.supervised.schemas import DatasetInput, DatasetRow, InvestorProfile, StartupProfile
from app.supervised.synthetic.export import validate_exports, file_hash

TEMPLATE = build_features(InvestorProfile(id="11111111-1111-4111-8111-111111111111"),
                          StartupProfile(id="22222222-2222-4222-8222-222222222222")).model_dump()
# Cidade é localização muito granular/quase identificadora; não se justifica neste ensaio.
EXCLUDED = {"investidor.cidade", "startup.cidade"}


def flatten(features):
    features = features.model_dump() if hasattr(features, 'model_dump') else features
    if set(features) != set(TEMPLATE) or any(set(features[g]) != set(TEMPLATE[g]) for g in TEMPLATE):
        raise ValueError("Features fora da lista permitida; metadados/target nunca são aceitos")
    result = {}
    for group, values in features.items():
        for key, value in values.items():
            if key in EXCLUDED:
                continue
            name = group + "::" + key
            if group == 'multivaloradas':
                result[name] = tuple(sorted(set(value)))
            elif group == 'categoricas' or (group == 'derivadas' and key.endswith('.estado')):
                result[name] = '__MISSING__' if value is None else str(value)
            else:
                result[name] = np.nan if value is None else float(value)
    return result


class MultiHot(BaseEstimator, TransformerMixin):
    """Vocabulário multivalorado aprendido só no treino; valores inéditos ignorados."""
    def _records(self, data):
        return [{f'{column}={token}': 1.0 for column in data.columns for token in row[column]}
                for _, row in data.iterrows()]

    def fit(self, X, y=None):
        self.vectorizer_ = DictVectorizer(sparse=True).fit(self._records(X))
        return self

    def transform(self, X):
        return self.vectorizer_.transform(self._records(X))

    def get_feature_names_out(self, input_features=None):
        return self.vectorizer_.get_feature_names_out()


class Preprocessor(BaseEstimator, TransformerMixin):
    """Descarta constantes/duplicatas exatas e ajusta encoders/imputação só em fit."""
    def fit(self, X, y=None):
        self.constant_, self.duplicates_, selected, signatures = [], {}, [], {}
        for column in X.columns:
            signature = tuple('__NA__' if isinstance(v, float) and np.isnan(v) else v for v in X[column])
            if len(set(signature)) <= 1:
                self.constant_.append(column)
            elif signature in signatures:
                self.duplicates_[column] = signatures[signature]
            else:
                signatures[signature] = column
                selected.append(column)
        self.selected_ = selected
        categorical = [c for c in selected if c.startswith('categoricas::') or c.endswith('.estado')]
        multi = [c for c in selected if c.startswith('multivaloradas::')]
        numeric = [c for c in selected if c not in categorical + multi]
        blocks = []
        if numeric:
            blocks.append(('numeric', Pipeline([('impute', SimpleImputer(strategy='median', keep_empty_features=True)), ('scale', StandardScaler())]), numeric))
        if categorical:
            blocks.append(('categorical', OneHotEncoder(handle_unknown='ignore', sparse_output=True), categorical))
        if multi:
            blocks.append(('multi', MultiHot(), multi))
        if not blocks:
            raise ValueError('Nenhuma feature variável no treino')
        self.transformer_ = ColumnTransformer(blocks, sparse_threshold=1.0)
        self.transformer_.fit(X)
        return self

    def transform(self, X):
        return self.transformer_.transform(X)

    def get_feature_names_out(self, input_features=None):
        return self.transformer_.get_feature_names_out()


@dataclass
class Prepared:
    rows: list
    frame: pd.DataFrame
    snapshots: dict
    audit: dict


def load_dataset(directory: Path):
    integrity = validate_exports(directory)
    raw = DatasetInput.model_validate_json((directory / 'input.json').read_bytes())
    rows = [DatasetRow.model_validate_json(line) for line in (directory / 'dataset.jsonl').open(encoding='utf-8')]
    rebuilt = build_dataset(raw)
    if rows != rebuilt.registros:
        raise ValueError('Dataset exportado difere do pipeline/snapshots originais')
    pairs, exposures = set(), set()
    for row in rows:
        meta = row.metadados
        pair = (meta['investidor_id'], meta['startup_id'])
        if pair in pairs or meta['exposicao_id'] in exposures:
            raise ValueError('Par ou exposição duplicado')
        pairs.add(pair)
        exposures.add(meta['exposicao_id'])
        if (meta['versao_contrato'], meta['versao_features'], meta['versao_target'], meta['origem_dados']) != (CONTRACT_VERSION, FEATURE_VERSION, TARGET_VERSION, 'sintetica'):
            raise ValueError('Versões/origem incompatíveis')
    labeled = [r for r in rows if r.rotulo.target is not None]
    with (directory / 'training.jsonl').open(encoding='utf-8') as stream:
        exported = [json.loads(line) for line in stream]
    if exported != [{'features': r.features.model_dump(mode='json'), 'target': r.rotulo.target} for r in labeled]:
        raise ValueError('training.jsonl não corresponde exatamente às linhas rotuladas')
    frame = pd.DataFrame([flatten(row.features) for row in rows])
    audit = {'integridade': integrity, 'manifest_sha256': file_hash(directory/'manifest.json'),
             'dataset_sha256': file_hash(directory/'dataset.jsonl'), 'origem': 'sintetica',
             'versoes': [CONTRACT_VERSION, FEATURE_VERSION, TARGET_VERSION],
             'pares_unicos': len(rows), 'rotulados': len(labeled), 'targets_nulos': len(rows)-len(labeled),
             'duplicatas': 0, 'atributos_originais': 57, 'indicadores_originais': 57,
             'excluidos_por_politica': sorted(EXCLUDED), 'colunas_candidatas': len(frame.columns),
             'missing_por_coluna': {c: int(frame[c].isna().sum()) for c in frame},
             'avaliacao_features': 'Somente atributos/scores de snapshot e indicadores. IDs, datas, posição, eventos, probabilidades latentes e labels ficam fora. Estados/flags redundantes são removidos se constantes ou idênticos no treino.'}
    return Prepared(rows, frame, {s.exposicao_id: s for s in raw.snapshots}, audit)
