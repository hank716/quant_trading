"""Tests for src/signals/predictor.py."""
import numpy as np
import pandas as pd
import pytest
import joblib
from pathlib import Path
from unittest.mock import MagicMock

from src.signals.predictor import predict, predict_from_champion
import src.signals.predictor as _pred_module


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

class _ConstantModel07:
    """Pickle-safe stub that always returns 0.7 probability."""
    def predict_proba(self, X):
        return np.array([[0.3, 0.7]] * len(X))


class _ConstantModel06:
    """Pickle-safe stub that always returns 0.6 probability."""
    def predict_proba(self, X):
        return np.array([[0.4, 0.6]] * len(X))


def _make_fake_model(tmp_path: Path, proba: float = 0.7):
    """Save a trivial sklearn-compatible model that always returns fixed proba."""
    stub = _ConstantModel07() if proba == 0.7 else _ConstantModel06()
    path = tmp_path / "fake_model.pkl"
    joblib.dump(stub, path)
    return path


def _make_registry(model_id: str, model_path: Path, champion: bool = False):
    """Build a minimal mock registry that serves a single model."""
    reg = MagicMock()
    reg.download_model.return_value = model_path
    if champion:
        reg.get_champion.return_value = {"model_id": model_id}
    else:
        reg.get_champion.return_value = None
    return reg


def _feature_df(n: int = 5) -> pd.DataFrame:
    instruments = [f"stock_{i:04d}" for i in range(n)]
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {"f1": rng.normal(0, 1, n), "f2": rng.normal(0, 1, n)},
        index=instruments,
    )


# ------------------------------------------------------------------ #
# predict
# ------------------------------------------------------------------ #

def test_predict_returns_correct_shape(tmp_path):
    pytest.importorskip("lightgbm")
    model_path = _make_fake_model(tmp_path)
    reg = _make_registry("m1", model_path)
    X = _feature_df(5)

    # clear in-process cache to ensure fresh load
    _pred_module._MODEL_CACHE.clear()

    result = predict(X, "m1", reg, cache_dir=tmp_path)
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 5
    assert list(result.columns) == ["instrument", "score", "model_id"]


def test_predict_scores_are_probabilities(tmp_path):
    model_path = _make_fake_model(tmp_path, proba=0.6)
    reg = _make_registry("m1", model_path)
    _pred_module._MODEL_CACHE.clear()
    result = predict(_feature_df(4), "m1", reg, cache_dir=tmp_path)
    assert (result["score"] >= 0).all() and (result["score"] <= 1).all()
    assert result["score"].to_numpy() == pytest.approx([0.6] * 4, rel=1e-3)


def test_predict_preserves_instrument_names(tmp_path):
    model_path = _make_fake_model(tmp_path)
    reg = _make_registry("m1", model_path)
    _pred_module._MODEL_CACHE.clear()
    X = _feature_df(3)
    result = predict(X, "m1", reg, cache_dir=tmp_path)
    assert list(result["instrument"]) == list(X.index)


def test_predict_model_id_column(tmp_path):
    model_path = _make_fake_model(tmp_path)
    reg = _make_registry("my_model_v2", model_path)
    _pred_module._MODEL_CACHE.clear()
    result = predict(_feature_df(2), "my_model_v2", reg, cache_dir=tmp_path)
    assert (result["model_id"] == "my_model_v2").all()


def test_predict_empty_returns_empty_df():
    reg = MagicMock()
    _pred_module._MODEL_CACHE.clear()
    result = predict(pd.DataFrame(), "m1", reg)
    assert result.empty
    assert list(result.columns) == ["instrument", "score", "model_id"]


def test_predict_uses_multiindex_instrument_level(tmp_path):
    model_path = _make_fake_model(tmp_path)
    reg = _make_registry("m1", model_path)
    _pred_module._MODEL_CACHE.clear()
    dates = pd.date_range("2024-01-01", periods=3, freq="B")
    instruments = ["2330", "2317", "2454"]
    idx = pd.MultiIndex.from_arrays([dates, instruments], names=["trade_date", "instrument"])
    X = pd.DataFrame({"f1": [0.1, 0.2, 0.3]}, index=idx)
    result = predict(X, "m1", reg, cache_dir=tmp_path)
    assert list(result["instrument"]) == instruments


# ------------------------------------------------------------------ #
# predict_from_champion
# ------------------------------------------------------------------ #

def test_predict_from_champion_returns_none_when_no_champion(tmp_path):
    reg = MagicMock()
    reg.get_champion.return_value = None
    result = predict_from_champion(_feature_df(3), "lgbm_binary", reg, cache_dir=tmp_path)
    assert result is None


def test_predict_from_champion_scores_with_champion(tmp_path):
    model_path = _make_fake_model(tmp_path)
    reg = _make_registry("champ_v1", model_path, champion=True)
    _pred_module._MODEL_CACHE.clear()
    result = predict_from_champion(_feature_df(4), "lgbm_binary", reg, cache_dir=tmp_path)
    assert result is not None
    assert len(result) == 4
    assert (result["model_id"] == "champ_v1").all()
