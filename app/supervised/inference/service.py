"""Loader lazy de um bundle local previamente autorizado por hashes externos."""

import hashlib
import importlib.metadata
import io
import json
import os
import platform
from functools import lru_cache
from pathlib import Path
from threading import Lock

from app.eligibility import evaluate_eligibility
from app.supervised.features import build_features
from app.supervised.inference.schemas import SupervisedRecommendation, SupervisedResponse

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / 'artifacts' / 'supervised'
DEFAULT_BUNDLE = ARTIFACTS / 'level2-seed42-validated'
REGISTRY = Path(__file__).with_name('trusted_model.json')
WARNINGS = [
    'Modelo experimental treinado com comportamento sintético; desempenho com usuários reais não validado.',
    'Probabilidade estimada de interesse em até 30 dias; não é score de compatibilidade do Nível 1A.',
    'Probabilidades não foram recalibradas com dados reais.',
]


class SupervisedUnavailable(Exception):
    """Erro público controlado; nunca expõe caminhos, pickle ou detalhes internos."""


def digest(value):
    return hashlib.sha256(value).hexdigest()


class Predictor:
    def __init__(self, bundle=None):
        self.bundle = Path(bundle if bundle is not None else os.getenv('SUPERVISED_MODEL_DIR', DEFAULT_BUNDLE))
        self._loaded = None
        self._lock = Lock()

    def load(self):
        if self._loaded is not None:
            return self._loaded
        with self._lock:
            if self._loaded is not None:
                return self._loaded
            try:
                self._loaded = self._load_trusted()
            except Exception as error:
                raise SupervisedUnavailable('Modelo supervisionado indisponível ou incompatível.') from error
            return self._loaded

    def _load_trusted(self):
        # Registro versionado é a âncora de confiança; não vem da requisição/bundle.
        trusted = json.loads(REGISTRY.read_text(encoding='utf-8'))
        directory = self.bundle.resolve(strict=True)
        if not directory.is_dir() or not directory.is_relative_to(ARTIFACTS.resolve()):
            raise ValueError('Bundle fora da raiz autorizada')
        verified = {}
        for relative, expected in trusted['files'].items():
            path = (directory / relative).resolve(strict=True)
            if not path.is_relative_to(directory):
                raise ValueError('Arquivo fora do bundle')
            content = path.read_bytes()
            if digest(content) != expected:
                raise ValueError('Hash de artefato incompatível')
            verified[relative] = content
        manifest = json.loads(verified['manifest.json'])
        for relative in ('metrics.json', 'temporal/metrics.json', 'temporal/xgboost.joblib'):
            if manifest['sha256'].get(relative) != trusted['files'][relative]:
                raise ValueError('Manifesto incompatível')
        for relative, expected in trusted['source_files'].items():
            # Normalizar CRLF/LF permite checkout sem mudança semântica de fonte.
            if digest((ROOT / relative).read_text(encoding='utf-8').encode()) != expected:
                raise ValueError('Código de features/contrato mudou desde a validação')
        metadata = json.loads(verified['metrics.json'])
        if metadata['data_audit']['versoes'] != ['supervised-v1','profiles-rules-v1','first-interest-v1'] or metadata['data_audit']['origem'] != 'sintetica':
            raise ValueError('Versão/origem incompatível')
        for package, expected in trusted['environment'].items():
            if package == 'python':
                if platform.python_version_tuple()[:2] != tuple(expected.split('.')[:2]):
                    raise ValueError('Versão Python incompatível')
            elif importlib.metadata.version(package) != expected:
                raise ValueError('Dependência incompatível')
        # Imports pesados e unpickle somente após todas as verificações anteriores.
        import joblib
        from sklearn.pipeline import Pipeline
        from xgboost import XGBClassifier
        from app.supervised.training.preparation import Preprocessor, flatten, TEMPLATE

        pipeline = joblib.load(io.BytesIO(verified['temporal/xgboost.joblib']))
        if type(pipeline) is not Pipeline or list(pipeline.named_steps) != ['preprocess','classifier']:
            raise ValueError('Pipeline inválido')
        processor, classifier = pipeline.named_steps['preprocess'], pipeline.named_steps['classifier']
        if type(processor) is not Preprocessor or type(classifier) is not XGBClassifier:
            raise ValueError('Tipos de pipeline incompatíveis')
        preprocessing = json.loads(verified['temporal/metrics.json'])['preprocessing']
        columns = list(flatten(TEMPLATE))
        if columns != trusted['input_columns'] or list(processor.transformer_.feature_names_in_) != columns:
            raise ValueError('Nomes/ordem de entrada incompatíveis')
        if processor.selected_ != preprocessing['selected_columns'] or processor.constant_ != preprocessing['constants_removed'] or processor.duplicates_ != preprocessing['exact_duplicates_removed']:
            raise ValueError('Seleção de features incompatível')
        encoded = list(processor.get_feature_names_out())
        if encoded != trusted['encoded_columns'] or classifier.n_features_in_ != len(encoded):
            raise ValueError('Features codificadas incompatíveis')
        if list(classifier.classes_) != [0,1]:
            raise ValueError('Classes incompatíveis')
        return pipeline, trusted

    def rank(self, payload):
        try:
            return self._rank(payload)
        except SupervisedUnavailable:
            raise
        except Exception as error:
            raise SupervisedUnavailable('Não foi possível produzir uma previsão supervisionada válida.') from error

    def _rank(self, payload):
        pipeline, trusted = self.load()
        import numpy as np
        import pandas as pd
        from app.supervised.training.preparation import flatten

        identity = {key:trusted[key] for key in ('modelo','versaoModelo','versaoContrato','versaoFeatures','versaoTarget')}
        candidates, features, warnings, excluded = [], [], [], []
        processor = pipeline.named_steps['preprocess']
        for startup in payload.startups:
            eligibility = evaluate_eligibility(payload.investidor, startup)
            if eligibility.estado == 'inelegivel':
                excluded.append({'startupId':startup.id,'elegibilidade':eligibility})
                continue
            values = flatten(build_features(payload.investidor, startup))
            missing = sum(values[name] == '__MISSING__' if isinstance(values[name],str) else
                          len(values[name]) == 0 if isinstance(values[name],tuple) else
                          bool(pd.isna(values[name])) for name in processor.selected_)
            notes = []
            if missing:
                notes.append(f'Perfil incompleto: {missing} entradas selecionadas ausentes; usado tratamento ajustado no treino.')
            if eligibility.estado == 'indeterminado':
                notes.append('Elegibilidade operacional indeterminada: ' + '; '.join(eligibility.pendencias))
            unknown = 0
            for name, transformer, columns in processor.transformer_.transformers_:
                if name == 'categorical':
                    unknown += sum(values[column] not in known for column,known in zip(columns,transformer.categories_))
                elif name == 'multi':
                    unknown += sum(f'{column}={token}' not in transformer.vectorizer_.vocabulary_ for column in columns for token in values[column])
            if unknown:
                notes.append(f'{unknown} categorias/itens não vistos no treino foram ignorados pelos encoders.')
            candidates.append(startup)
            features.append(values)
            warnings.append(notes)
        recommendations = []
        if candidates:
            frame = pd.DataFrame(features, columns=trusted['input_columns'])
            probability = np.asarray(pipeline.predict_proba(frame))
            if probability.shape != (len(candidates),2) or not np.all(np.isfinite(probability)) or np.any((probability<0)|(probability>1)) or not np.allclose(probability.sum(axis=1),1,rtol=0,atol=1e-6):
                raise ValueError('Probabilidades inválidas')
            ordered = sorted(zip(candidates,probability[:,1],warnings), key=lambda item:(-float(item[1]),str(item[0].id)))
            recommendations = [SupervisedRecommendation(**identity,startupId=startup.id,posicao=index+1,
                                probabilidadeInteresse=float(score),avisos=notes)
                               for index,(startup,score,notes) in enumerate(ordered[:payload.limite])]
        return SupervisedResponse(**identity,investidorId=payload.investidor.id,recomendacoes=recommendations,
                                  excluidas=sorted(excluded,key=lambda row:str(row['startupId'])),avisos=list(WARNINGS))


@lru_cache(maxsize=1)
def get_predictor():
    return Predictor()
