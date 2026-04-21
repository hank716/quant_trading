"""Unit tests for src/monitoring/coverage_checker.py"""
from datetime import date

import pandas as pd
import pytest

from src.monitoring.coverage_checker import (
    build_coverage_snapshot,
    compute_financial_coverage,
    compute_revenue_coverage,
    find_missing_critical,
)

TRADE_DATE = date(2026, 4, 21)
_DUMMY_DF = pd.DataFrame({"revenue": [100]})


# ------------------------------------------------------------------ #
# compute_revenue_coverage
# ------------------------------------------------------------------ #

def test_revenue_coverage_full():
    universe = ["2330", "2317", "2454"]
    rev_map = {sid: _DUMMY_DF.copy() for sid in universe}
    result = compute_revenue_coverage(universe, rev_map, TRADE_DATE)
    assert result["coverage_pct"] == 1.0
    assert result["covered"] == 3
    assert result["missing"] == []


def test_revenue_coverage_partial():
    universe = ["2330", "2317", "2454", "3008"]
    rev_map = {"2330": _DUMMY_DF.copy(), "3008": _DUMMY_DF.copy()}
    result = compute_revenue_coverage(universe, rev_map, TRADE_DATE)
    assert result["coverage_pct"] == 0.5
    assert result["covered"] == 2
    assert set(result["missing"]) == {"2317", "2454"}


def test_revenue_coverage_empty_data():
    universe = ["2330", "2317"]
    result = compute_revenue_coverage(universe, {}, TRADE_DATE)
    assert result["coverage_pct"] == 0.0
    assert result["covered"] == 0
    assert len(result["missing"]) == 2


def test_revenue_coverage_empty_universe():
    result = compute_revenue_coverage([], {}, TRADE_DATE)
    assert result["coverage_pct"] == 0.0
    assert result["total"] == 0


def test_revenue_coverage_empty_df_in_map():
    universe = ["2330", "2317"]
    rev_map = {"2330": _DUMMY_DF.copy(), "2317": pd.DataFrame()}
    result = compute_revenue_coverage(universe, rev_map, TRADE_DATE)
    assert result["coverage_pct"] == 0.5
    assert "2317" in result["missing"]


# ------------------------------------------------------------------ #
# compute_financial_coverage
# ------------------------------------------------------------------ #

def test_financial_coverage_full():
    universe = ["2330", "2317"]
    fin_map = {sid: _DUMMY_DF.copy() for sid in universe}
    result = compute_financial_coverage(universe, fin_map, TRADE_DATE)
    assert result["coverage_pct"] == 1.0


def test_financial_coverage_empty():
    universe = ["2330", "2317", "2454"]
    result = compute_financial_coverage(universe, {}, TRADE_DATE)
    assert result["coverage_pct"] == 0.0
    assert result["total"] == 3


# ------------------------------------------------------------------ #
# find_missing_critical
# ------------------------------------------------------------------ #

def test_find_missing_critical_none_missing():
    coverage = {"missing": ["9999"]}
    assert find_missing_critical(coverage, ["2330", "2317"]) == []


def test_find_missing_critical_some_missing():
    coverage = {"missing": ["2330", "9999"]}
    result = find_missing_critical(coverage, ["2330", "2317", "0050"])
    assert result == ["2330"]


def test_find_missing_critical_empty_critical_list():
    coverage = {"missing": ["2330"]}
    assert find_missing_critical(coverage, []) == []


# ------------------------------------------------------------------ #
# build_coverage_snapshot
# ------------------------------------------------------------------ #

def test_build_snapshot_structure():
    rev = {"coverage_pct": 0.85, "covered": 850, "total": 1000}
    fin = {"coverage_pct": 0.60, "covered": 600, "total": 1000}
    snap = build_coverage_snapshot(TRADE_DATE, rev, fin, missing_critical=["2330"])
    assert snap["trade_date"] == "2026-04-21"
    assert snap["revenue_coverage"] == 0.85
    assert snap["financial_coverage"] == 0.60
    assert snap["missing_critical"] == ["2330"]
    assert "revenue_covered" in snap
    assert "financial_covered" in snap


def test_build_snapshot_no_critical():
    rev = {"coverage_pct": 1.0, "covered": 10, "total": 10}
    fin = {"coverage_pct": 1.0, "covered": 10, "total": 10}
    snap = build_coverage_snapshot(TRADE_DATE, rev, fin)
    assert snap["missing_critical"] == []
