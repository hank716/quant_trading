"""Unit tests for TwTopkFilteredStrategy filter logic."""
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch


def _make_score(symbols):
    return pd.Series([0.9, 0.8, 0.7, 0.6, 0.5][:len(symbols)], index=symbols)


def test_filter_removes_exclude_symbols():
    from qlib_ext.strategies.tw_topk_filtered import TwTopkFilteredStrategy
    strat = TwTopkFilteredStrategy.__new__(TwTopkFilteredStrategy)
    strat.exclude_symbols = {"BAD.TW", "ALSO_BAD.TW"}
    strat.min_price = 0.0
    strat.min_listing_days = 0
    strat._listing_start = {}

    score = _make_score(["GOOD.TW", "BAD.TW", "OK.TW", "ALSO_BAD.TW", "FINE.TW"])
    result = strat._filter_universe(score, None)
    assert "BAD.TW" not in result.index
    assert "ALSO_BAD.TW" not in result.index
    assert len(result) == 3


def test_filter_empty_exclude():
    from qlib_ext.strategies.tw_topk_filtered import TwTopkFilteredStrategy
    strat = TwTopkFilteredStrategy.__new__(TwTopkFilteredStrategy)
    strat.exclude_symbols = set()
    strat.min_price = 0.0
    strat.min_listing_days = 0
    strat._listing_start = {}

    score = _make_score(["A.TW", "B.TW", "C.TW"])
    result = strat._filter_universe(score, None)
    assert len(result) == 3


def test_filter_listing_days():
    from qlib_ext.strategies.tw_topk_filtered import TwTopkFilteredStrategy
    strat = TwTopkFilteredStrategy.__new__(TwTopkFilteredStrategy)
    strat.exclude_symbols = set()
    strat.min_price = 0.0
    strat.min_listing_days = 180
    strat._listing_start = {
        "NEW.TW": "2026-03-01",   # listed 52 days before 2026-04-22
        "OLD.TW": "2025-01-01",   # listed > 180 days
    }

    score = _make_score(["NEW.TW", "OLD.TW"])
    result = strat._filter_universe(score, "2026-04-22")
    assert "NEW.TW" not in result.index
    assert "OLD.TW" in result.index


def test_filter_returns_series_type():
    from qlib_ext.strategies.tw_topk_filtered import TwTopkFilteredStrategy
    strat = TwTopkFilteredStrategy.__new__(TwTopkFilteredStrategy)
    strat.exclude_symbols = set()
    strat.min_price = 0.0
    strat.min_listing_days = 0
    strat._listing_start = {}

    score = _make_score(["X.TW", "Y.TW"])
    result = strat._filter_universe(score, None)
    assert isinstance(result, pd.Series)
