"""Tests for src/signals/labeler.py"""
import pandas as pd
import pytest
from src.signals.labeler import binary_label, compute_forward_return


def _price_df(closes: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    return pd.DataFrame({"date": dates, "close": closes})


def test_forward_return_basic():
    df = _price_df([100.0, 110.0, 121.0, 133.1, 146.4])
    result = compute_forward_return(df, horizon_days=1)
    assert result.iloc[0] == pytest.approx(0.10, rel=1e-3)
    assert pd.isna(result.iloc[-1])


def test_forward_return_horizon_fills_nan_tail():
    df = _price_df(list(range(1, 11)))  # 10 rows
    result = compute_forward_return(df, horizon_days=3)
    assert result.notna().sum() == 7
    assert result.isna().sum() == 3


def test_forward_return_empty_df():
    result = compute_forward_return(pd.DataFrame(), horizon_days=5)
    assert len(result) == 0


def test_forward_return_missing_columns():
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=3), "open": [1, 2, 3]})
    result = compute_forward_return(df, horizon_days=1)
    assert len(result) == 0


def test_binary_label_positive():
    s = pd.Series([0.05, 0.10, -0.03, 0.0], dtype=float)
    labels = binary_label(s, threshold=0.0)
    assert list(labels) == [1, 1, 0, 0]


def test_binary_label_custom_threshold():
    s = pd.Series([0.05, 0.03, 0.01], dtype=float)
    labels = binary_label(s, threshold=0.04)
    assert list(labels) == [1, 0, 0]


def test_binary_label_propagates_nan():
    s = pd.Series([0.05, float("nan"), -0.01])
    labels = binary_label(s)
    assert labels.iloc[0] == 1
    assert pd.isna(labels.iloc[1])
    assert labels.iloc[2] == 0
