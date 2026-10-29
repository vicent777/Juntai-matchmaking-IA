"""Preparação offline de dados; sem treinamento, HTTP ou persistência."""

from app.supervised.dataset import build_dataset
from app.supervised.schemas import DatasetInput

__all__ = ["build_dataset", "DatasetInput"]
