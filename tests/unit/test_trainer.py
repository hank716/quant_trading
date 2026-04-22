"""Tests for src/signals/trainer.py — uses a tiny synthetic dataset."""
import numpy as np
import pandas as pd
import pytest
from src.signals.trainer import save_model, train, walk_forward_split


def _dummy_dataset(n: int = 60, seed: int = 0) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    X = pd.DataFrame(
        {
            "f1": rng.normal(0, 1, n),
            "f2": rng.normal(0, 1, n),
            "f3": rng.uniform(0, 1, n),
        },
        index=dates,
    )
    y = pd.Series((rng.normal(0, 1, n) > 0).astype(int), index=dates, name="label")
    return X, y


# --- walk_forward_split ---

def test_walk_forward_split_returns_correct_count():
    df = pd.DataFrame({"date": pd.date_range("2023-01-01", periods=30, freq="B")})
    splits = walk_forward_split(df, "date", n_splits=3)
    assert len(splits) == 3


def test_walk_forward_split_train_before_val():
    df = pd.DataFrame({"date": pd.date_range("2023-01-01", periods=40, freq="B")})
    splits = walk_forward_split(df, "date", n_splits=3)
    for train_idx, val_idx in splits:
        assert max(train_idx) < min(val_idx)


def test_walk_forward_split_empty():
    splits = walk_forward_split(pd.DataFrame(columns=["date"]), "date", n_splits=3)
    assert splits == []


def test_walk_forward_split_zero_splits():
    df = pd.DataFrame({"date": pd.date_range("2023-01-01", periods=10, freq="B")})
    splits = walk_forward_split(df, "date", n_splits=0)
    assert splits == []


# --- train ---

def test_train_returns_model_and_metrics():
    pytest.importorskip("lightgbm")
    X, y = _dummy_dataset(60)
    model, metrics = train(X, y)
    assert model is not None
    assert "auc" in metrics
    assert "n_train" in metrics and "n_val" in metrics
    assert metrics["n_train"] + metrics["n_val"] == len(X)


def test_train_too_few_samples_raises():
    pytest.importorskip("lightgbm")
    X, y = _dummy_dataset(5)
    with pytest.raises(ValueError, match="Too few"):
        train(X, y)


def test_train_custom_params():
    pytest.importorskip("lightgbm")
    X, y = _dummy_dataset(60)
    model, metrics = train(X, y, params={"n_estimators": 10})
    assert metrics["n_features"] == 3


# --- save_model ---

def test_save_model_creates_file(tmp_path):
    pytest.importorskip("lightgbm")
    X, y = _dummy_dataset(60)
    model, _ = train(X, y)
    path = save_model(model, "test_model_v1", tmp_path)
    assert path.exists()
    assert path.suffix == ".pkl"
    assert path.stem == "test_model_v1"


def test_save_model_creates_output_dir(tmp_path):
    pytest.importorskip("lightgbm")
    X, y = _dummy_dataset(60)
    model, _ = train(X, y)
    nested = tmp_path / "deep" / "path"
    path = save_model(model, "m1", nested)
    assert path.exists()
