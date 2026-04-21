"""Unit tests for src/features/tech_features.py"""
import pandas as pd
import pytest

from src.features.tech_features import (
    institutional_flow_features,
    ma_return,
    volume_features,
)


def _price_df(closes: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    data = {"date": pd.date_range("2026-01-01", periods=len(closes), freq="B"), "close": closes}
    if volumes:
        data["Trading_Volume"] = volumes
    return pd.DataFrame(data)


def _flow_df(buy_sell: list[tuple[float, float]]) -> pd.DataFrame:
    rows = [{"date": f"2026-01-{i+1:02d}", "name": "外資", "buy": b, "sell": s}
            for i, (b, s) in enumerate(buy_sell)]
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ #
# ma_return
# ------------------------------------------------------------------ #

def test_ma_return_basic():
    prices = [100.0] * 10 + [110.0]  # 11 days, last close 110
    df = _price_df(prices)
    result = ma_return(df, windows=[5])
    # MA(5) of [110,100,100,100,100] = 102; return = 110/102 - 1 ≈ 0.0784
    assert result["tech_ma5_ret"] is not None
    assert result["tech_ma5_ret"] > 0  # above MA


def test_ma_return_all_windows():
    prices = list(range(1, 70))  # 69 days
    df = _price_df(prices)
    result = ma_return(df, windows=[5, 10, 20, 60])
    assert all(result[f"tech_ma{w}_ret"] is not None for w in [5, 10, 20, 60])


def test_ma_return_insufficient_history():
    df = _price_df([100.0, 101.0])  # only 2 days
    result = ma_return(df, windows=[5, 20])
    assert result["tech_ma5_ret"] is None
    assert result["tech_ma20_ret"] is None


def test_ma_return_empty_df():
    result = ma_return(pd.DataFrame(), windows=[5])
    assert result["tech_ma5_ret"] is None


def test_ma_return_missing_close_col():
    df = pd.DataFrame({"date": ["2026-01-01"], "price": [100.0]})
    result = ma_return(df, windows=[5])
    assert result["tech_ma5_ret"] is None


# ------------------------------------------------------------------ #
# volume_features
# ------------------------------------------------------------------ #

def test_volume_features_high_recent():
    vols = [100.0] * 20 + [500.0] * 5  # last 5 days: 5x normal
    df = _price_df([1.0] * 25, volumes=vols)
    result = volume_features(df, windows=[5])
    assert result["tech_vol5_ratio"] is not None
    assert result["tech_vol5_ratio"] > 1.0


def test_volume_features_no_volume_col():
    df = pd.DataFrame({"date": ["2026-01-01"], "close": [100.0]})
    result = volume_features(df, windows=[5])
    assert result["tech_vol5_ratio"] is None


def test_volume_features_empty():
    result = volume_features(pd.DataFrame(), windows=[5, 20])
    assert result["tech_vol5_ratio"] is None
    assert result["tech_vol20_ratio"] is None


# ------------------------------------------------------------------ #
# institutional_flow_features
# ------------------------------------------------------------------ #

def test_flow_net_buying():
    buy_sell = [(1000.0, 200.0)] * 10  # net buy every day
    df = _flow_df(buy_sell)
    result = institutional_flow_features(df, windows=[5])
    assert result["tech_fi_net5_ratio"] is not None
    assert result["tech_fi_net5_ratio"] > 0


def test_flow_net_selling():
    buy_sell = [(200.0, 1000.0)] * 10  # net sell every day
    df = _flow_df(buy_sell)
    result = institutional_flow_features(df, windows=[5])
    assert result["tech_fi_net5_ratio"] < 0


def test_flow_empty():
    result = institutional_flow_features(pd.DataFrame(), windows=[5])
    assert result["tech_fi_net5_ratio"] is None


def test_flow_missing_columns():
    df = pd.DataFrame({"date": ["2026-01-01"], "buy": [100.0]})  # missing 'sell'
    result = institutional_flow_features(df, windows=[5])
    assert result["tech_fi_net5_ratio"] is None
