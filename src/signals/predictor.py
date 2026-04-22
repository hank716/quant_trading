"""LightGBM predictor — load champion model and score a feature matrix."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import pandas as pd

if TYPE_CHECKING:
    from src.registry.model_registry import ModelRegistry

logger = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, object] = {}


def _load_model(model_id: str, registry: "ModelRegistry", cache_dir: Optional[Path] = None):
    """Load (and cache in-process) a model by model_id."""
    if model_id in _MODEL_CACHE:
        return _MODEL_CACHE[model_id]

    import joblib

    cache_dir = cache_dir or Path("workspace/runs/models")
    local_path = registry.download_model(model_id, cache_dir)
    model = joblib.load(local_path)
    _MODEL_CACHE[model_id] = model
    logger.info("Loaded model %s from %s", model_id, local_path)
    return model


def predict(
    feature_matrix: pd.DataFrame,
    model_id: str,
    registry: "ModelRegistry",
    cache_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """Score *feature_matrix* with the given model.

    Args:
        feature_matrix: DataFrame with features as columns; index should be
            ``(trade_date, instrument)`` or just ``instrument``.
        model_id: identifier of the model to load from the registry.
        registry: ModelRegistry instance.
        cache_dir: local directory used to cache downloaded model files.

    Returns:
        DataFrame with columns ``[instrument, score, model_id]``.
        ``score`` is the predicted probability of the positive class (binary).
    """
    if feature_matrix.empty:
        return pd.DataFrame(columns=["instrument", "score", "model_id"])

    model = _load_model(model_id, registry, cache_dir)

    X = feature_matrix.copy().fillna(0.0)
    try:
        probas = model.predict_proba(X)[:, 1]
    except Exception as exc:
        raise RuntimeError(f"Model prediction failed for {model_id}: {exc}") from exc

    # resolve instrument names from index
    idx = feature_matrix.index
    if isinstance(idx, pd.MultiIndex):
        instruments = idx.get_level_values(-1).tolist()
    else:
        instruments = idx.tolist()

    return pd.DataFrame({
        "instrument": instruments,
        "score": probas,
        "model_id": model_id,
    })


def predict_from_champion(
    feature_matrix: pd.DataFrame,
    family: str,
    registry: "ModelRegistry",
    cache_dir: Optional[Path] = None,
) -> Optional[pd.DataFrame]:
    """Convenience wrapper: load the champion for *family* and score.

    Returns None (and logs a warning) if no champion exists.
    """
    champion = registry.get_champion(family)
    if champion is None:
        logger.warning("No champion model found for family=%s; skipping ML scoring", family)
        return None

    model_id = champion["model_id"]
    logger.info("Scoring with champion model: %s (family=%s)", model_id, family)
    return predict(feature_matrix, model_id, registry, cache_dir)
