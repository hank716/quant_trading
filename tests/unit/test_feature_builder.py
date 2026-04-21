"""Unit tests for src/features/feature_builder.py"""
from datetime import date

import pandas as pd
import pytest

from src.features.feature_builder import build_feature_matrix

TRADE_DATE = date(2026, 4, 21)


def _make_price(n: int = 30) -> pd.DataFrame:
    closes = list(range(100, 100 + n))
    vols = [1000.0] * n
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n, freq="B"),
        "close": closes,
        "Trading_Volume": vols,
    })


def _make_flow(n: int = 10) -> pd.DataFrame:
    rows = [{"date": f"2026-01-{i+1:02d}", "name": "外資", "buy": 500.0, "sell": 100.0}
            for i in range(n)]
    return pd.DataFrame(rows)


def _make_revenue(n: int = 4) -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.date_range("2025-10-01", periods=n, freq="MS"),
        "revenue": [1000.0, 1100.0, 1050.0, 1200.0],
        "revenue_yoy": [0.05, 0.10, 0.08, 0.15],
    })


def _make_financial(n: int = 3) -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=n, freq="QS"),
        "roe_percent": [12.0, 14.0, 15.0],
        "gross_margin_percent": [38.0, 40.0, 42.0],
    })


# ------------------------------------------------------------------ #
# Structure
# ------------------------------------------------------------------ #

def test_output_shape_and_index():
    universe = ["2330", "2317"]
    price_map = {sid: _make_price() for sid in universe}
    flow_map = {sid: _make_flow() for sid in universe}
    rev_map = {sid: _make_revenue() for sid in universe}
    fin_map = {sid: _make_financial() for sid in universe}

    df = build_feature_matrix(universe, price_map, flow_map, rev_map, fin_map, TRADE_DATE)

    assert len(df) == 2
    assert df.index.names == ["trade_date", "instrument"]
    assert "2330" in df.index.get_level_values("instrument")


def test_all_expected_columns_present():
    universe = ["2330"]
    price_map = {"2330": _make_price()}
    flow_map = {"2330": _make_flow()}
    rev_map = {"2330": _make_revenue()}
    fin_map = {"2330": _make_financial()}

    df = build_feature_matrix(universe, price_map, flow_map, rev_map, fin_map, TRADE_DATE)

    tech_cols = ["tech_ma5_ret", "tech_ma10_ret", "tech_ma20_ret", "tech_ma60_ret",
                 "tech_vol5_ratio", "tech_vol20_ratio",
                 "tech_fi_net5_ratio", "tech_fi_net20_ratio"]
    fund_cols = ["fund_rev_yoy", "fund_rev_mom", "fund_rev_consec_pos",
                 "fund_roe", "fund_roe_yoy", "fund_gm", "fund_gm_yoy"]
    for col in tech_cols + fund_cols:
        assert col in df.columns, f"Missing column: {col}"


# ------------------------------------------------------------------ #
# NaN filling
# ------------------------------------------------------------------ #

def test_nan_filled_with_cross_section_median():
    universe = ["A", "B", "C"]
    # A has full data, B and C have no price
    price_map = {"A": _make_price(), "B": pd.DataFrame(), "C": pd.DataFrame()}
    flow_map = {sid: pd.DataFrame() for sid in universe}
    rev_map = {sid: pd.DataFrame() for sid in universe}
    fin_map = {sid: pd.DataFrame() for sid in universe}

    df = build_feature_matrix(universe, price_map, flow_map, rev_map, fin_map, TRADE_DATE)

    # tech_ma5_ret for B and C should be filled with A's value (only non-null)
    vals = df["tech_ma5_ret"].dropna()
    assert len(vals) == 3  # all filled


def test_empty_universe_returns_empty_df():
    df = build_feature_matrix([], {}, {}, {}, {}, TRADE_DATE)
    assert df.empty


def test_all_empty_maps_no_error():
    universe = ["2330"]
    df = build_feature_matrix(
        universe, {}, {}, {}, {}, TRADE_DATE
    )
    assert len(df) == 1
    # All NaN initially; median fill can't help if only 1 stock → stays NaN
    # But no exception raised
