"""Unit tests for src/features/fund_features.py"""
import pandas as pd
import pytest

from src.features.fund_features import gross_margin_feature, revenue_momentum, roe_feature


def _rev_df(revenues: list[float], yoy: list[float] | None = None) -> pd.DataFrame:
    n = len(revenues)
    data: dict = {
        "date": pd.date_range("2024-01-01", periods=n, freq="MS"),
        "revenue": revenues,
    }
    if yoy:
        data["revenue_yoy"] = yoy  # stored as fraction (e.g. 0.15)
    return pd.DataFrame(data)


def _fin_df(roe_vals: list[float], gm_vals: list[float] | None = None) -> pd.DataFrame:
    data: dict = {
        "date": pd.date_range("2023-01-01", periods=len(roe_vals), freq="QS"),
        "roe_percent": roe_vals,
    }
    if gm_vals:
        data["gross_margin_percent"] = gm_vals
    return pd.DataFrame(data)


# ------------------------------------------------------------------ #
# revenue_momentum
# ------------------------------------------------------------------ #

def test_rev_momentum_with_precomputed_yoy():
    df = _rev_df([100, 110, 120], yoy=[0.05, 0.10, 0.15])
    result = revenue_momentum(df)
    assert result["fund_rev_yoy"] == pytest.approx(0.15, abs=1e-4)


def test_rev_momentum_consec_positive():
    # 4 months all positive YoY
    df = _rev_df([100] * 4, yoy=[0.05, 0.08, 0.10, 0.12])
    result = revenue_momentum(df)
    assert result["fund_rev_consec_pos"] == 4


def test_rev_momentum_breaks_streak():
    df = _rev_df([100] * 5, yoy=[0.10, 0.05, -0.02, 0.08, 0.12])
    result = revenue_momentum(df)
    # Streak should be 2 (last two are positive: 0.08, 0.12)
    assert result["fund_rev_consec_pos"] == 2


def test_rev_momentum_empty():
    result = revenue_momentum(pd.DataFrame())
    assert result["fund_rev_yoy"] is None
    assert result["fund_rev_consec_pos"] is None


def test_rev_momentum_percentage_normalisation():
    # YoY stored as percentage (e.g. 15.0 instead of 0.15)
    df = _rev_df([100], yoy=[15.0])
    result = revenue_momentum(df)
    assert result["fund_rev_yoy"] == pytest.approx(0.15, abs=1e-4)


# ------------------------------------------------------------------ #
# roe_feature
# ------------------------------------------------------------------ #

def test_roe_basic():
    df = _fin_df([10.0, 12.0, 15.0])  # stored as percentage
    result = roe_feature(df)
    assert result["fund_roe"] == pytest.approx(0.15, abs=1e-4)
    assert result["fund_roe_yoy"] == pytest.approx(0.03, abs=1e-4)  # 0.15 - 0.12


def test_roe_single_period_no_yoy():
    df = _fin_df([20.0])
    result = roe_feature(df)
    assert result["fund_roe"] is not None
    assert result["fund_roe_yoy"] is None


def test_roe_empty():
    result = roe_feature(pd.DataFrame())
    assert result["fund_roe"] is None


def test_roe_fraction_stored():
    df = _fin_df([0.15, 0.18])  # stored as fraction
    result = roe_feature(df)
    assert result["fund_roe"] == pytest.approx(0.18, abs=1e-4)


# ------------------------------------------------------------------ #
# gross_margin_feature
# ------------------------------------------------------------------ #

def test_gm_basic():
    df = _fin_df([10.0, 11.0], gm_vals=[40.0, 45.0])  # roe dummy, gm as %
    result = gross_margin_feature(df)
    assert result["fund_gm"] == pytest.approx(0.45, abs=1e-4)
    assert result["fund_gm_yoy"] == pytest.approx(0.05, abs=1e-4)


def test_gm_empty():
    result = gross_margin_feature(pd.DataFrame())
    assert result["fund_gm"] is None
