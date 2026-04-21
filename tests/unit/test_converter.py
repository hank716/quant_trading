from datetime import date

import pytest

from core.models import DailyResult, Candidate
from src.reporting.converter import (
    daily_result_to_signals,
    daily_result_to_positions,
    daily_result_to_trades,
    daily_result_to_report,
    build_manifest,
)


def _make_result(eligible=2, watch=1):
    eligible_list = [
        Candidate(asset=f"stock_{i}", name=f"名稱{i}", market="twse",
                  score=0.9 - i * 0.1, why=["動能強"])
        for i in range(eligible)
    ]
    watch_list = [
        Candidate(asset=f"watch_{i}", name=f"觀察{i}", market="twse", score=0.5)
        for i in range(watch)
    ]
    return DailyResult(
        date="2026-04-21",
        strategy="test_strategy",
        action="consider",
        selection_mode="rule_based",
        eligible_candidates=eligible_list,
        watch_only_candidates=watch_list,
        notes=["note1", "note2", "note3"],
    )


def test_signals_count():
    result = _make_result(eligible=2, watch=1)
    signals = daily_result_to_signals(result)
    assert len(signals) == 3  # 2 eligible + 1 watch


def test_signals_watch_score_halved():
    result = _make_result(eligible=0, watch=1)
    signals = daily_result_to_signals(result)
    assert signals[0].score == pytest.approx(0.25)  # 0.5 * 0.5


def test_positions_equal_weight():
    result = _make_result(eligible=4, watch=0)
    positions = daily_result_to_positions(result)
    assert len(positions) == 4
    assert all(p.target_weight == pytest.approx(0.25) for p in positions)


def test_positions_empty_eligible():
    result = _make_result(eligible=0, watch=1)
    positions = daily_result_to_positions(result)
    assert positions == []


def test_trades_buy_on_new_entry():
    result = _make_result(eligible=2, watch=0)
    trades = daily_result_to_trades(result, prev_positions=[])
    buys = [t for t in trades if t.action == "BUY"]
    assert len(buys) == 2


def test_trades_sell_on_exit():
    from src.portfolio.schema import PositionRecord
    prev = [PositionRecord(trade_date=date(2026, 4, 20), instrument="stock_0",
                           target_weight=0.5, notional=0, score=0.9,
                           selection_reason="")]
    result = _make_result(eligible=0, watch=0)
    trades = daily_result_to_trades(result, prev_positions=prev)
    sells = [t for t in trades if t.action == "SELL"]
    assert len(sells) == 1
    assert sells[0].instrument == "stock_0"


def test_report_has_correct_summary():
    result = _make_result(eligible=3, watch=1)
    report = daily_result_to_report(result, {"signals": "signals.json"})
    assert "consider=3" in report.position_change_summary
    assert "watch=1" in report.position_change_summary
    assert report.disclaimer == "本報告僅供研究，非投資建議"


def test_manifest_fields():
    result = _make_result()
    manifest = build_manifest("run_001", date(2026, 4, 21), result, {})
    assert manifest.run_id == "run_001"
    assert manifest.status == "success"
    assert manifest.trade_date == date(2026, 4, 21)
    assert manifest.mode == "daily"
