"""Unit tests for src/registry/retrain_gate.py — minimum 6 cases."""
from datetime import date

import pytest

from src.registry.retrain_gate import build_retrain_decision, should_trigger_retrain

TODAY = date(2026, 4, 21)

_HEALTHY_SNAPSHOT = {
    "trade_date": "2026-04-21",
    "revenue_coverage": 0.90,
    "financial_coverage": 0.75,
    "missing_critical": [],
}


# ------------------------------------------------------------------ #
# should_trigger_retrain
# ------------------------------------------------------------------ #

def test_no_previous_retrain_triggers():
    trigger, reason = should_trigger_retrain(_HEALTHY_SNAPSHOT, None, today=TODAY)
    assert trigger is True
    assert "no previous retrain" in reason


def test_recent_retrain_does_not_trigger():
    last = date(2026, 4, 10)  # 11 days ago
    trigger, reason = should_trigger_retrain(
        _HEALTHY_SNAPSHOT, last, today=TODAY, min_days=30
    )
    assert trigger is False
    assert "11/30" in reason


def test_min_days_elapsed_triggers():
    last = date(2026, 3, 20)  # 32 days ago
    trigger, reason = should_trigger_retrain(
        _HEALTHY_SNAPSHOT, last, today=TODAY, min_days=30
    )
    assert trigger is True
    assert "32 days" in reason


def test_low_revenue_coverage_triggers():
    snap = {**_HEALTHY_SNAPSHOT, "revenue_coverage": 0.50}
    trigger, reason = should_trigger_retrain(
        snap, date(2026, 4, 10), today=TODAY, revenue_threshold=0.70
    )
    assert trigger is True
    assert "revenue_coverage" in reason


def test_low_financial_coverage_triggers():
    snap = {**_HEALTHY_SNAPSHOT, "financial_coverage": 0.40}
    trigger, reason = should_trigger_retrain(
        snap, date(2026, 4, 10), today=TODAY, financial_threshold=0.60
    )
    assert trigger is True
    assert "financial_coverage" in reason


def test_missing_critical_triggers():
    snap = {**_HEALTHY_SNAPSHOT, "missing_critical": ["2330", "0050"]}
    trigger, reason = should_trigger_retrain(
        snap, date(2026, 4, 10), today=TODAY, max_missing_critical=0
    )
    assert trigger is True
    assert "critical" in reason


def test_all_healthy_no_trigger():
    last = date(2026, 4, 15)  # 6 days ago
    trigger, _ = should_trigger_retrain(
        _HEALTHY_SNAPSHOT, last, today=TODAY,
        min_days=30, revenue_threshold=0.70,
        financial_threshold=0.60, max_missing_critical=0,
    )
    assert trigger is False


# ------------------------------------------------------------------ #
# build_retrain_decision
# ------------------------------------------------------------------ #

def test_build_decision_structure():
    last = date(2026, 3, 20)
    decision = build_retrain_decision(_HEALTHY_SNAPSHOT, last, today=TODAY, min_days=30)
    assert "should_retrain" in decision
    assert decision["should_retrain"] is True
    assert decision["days_since_retrain"] == 32
    assert decision["last_retrain_date"] == "2026-03-20"
    assert "revenue_coverage" in decision


def test_build_decision_no_previous_retrain():
    decision = build_retrain_decision(_HEALTHY_SNAPSHOT, None, today=TODAY)
    assert decision["should_retrain"] is True
    assert decision["last_retrain_date"] is None
    assert decision["days_since_retrain"] is None
