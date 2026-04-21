"""Contract tests: verify artifact schemas have required fields and correct types."""
import json
from datetime import date, datetime

import pytest

from src.signals.schema import SignalRecord
from src.portfolio.schema import PositionRecord, TradeRecord
from src.reporting.schema import DailyReportArtifact, RunManifest


def test_signal_record_required_fields():
    r = SignalRecord(trade_date=date(2026, 4, 21), instrument="2330",
                     score=0.9, model_id="m1", data_snapshot_id="s1")
    assert r.bar_freq == "1d"
    assert r.feature_set_version == "v1"
    d = r.model_dump()
    for field in ("trade_date", "instrument", "score", "model_id", "data_snapshot_id"):
        assert field in d


def test_position_record_weight_bounds():
    with pytest.raises(Exception):
        PositionRecord(trade_date=date(2026, 4, 21), instrument="x",
                       target_weight=1.5, notional=0, score=0, selection_reason="")
    with pytest.raises(Exception):
        PositionRecord(trade_date=date(2026, 4, 21), instrument="x",
                       target_weight=-0.1, notional=0, score=0, selection_reason="")


def test_trade_record_valid_actions():
    for action in ("BUY", "SELL", "HOLD"):
        t = TradeRecord(trade_date=date(2026, 4, 21), instrument="x",
                        action=action, delta_weight=0.0, prev_weight=0.0,
                        new_weight=0.0, reason="test")
        assert t.action == action

    with pytest.raises(Exception):
        TradeRecord(trade_date=date(2026, 4, 21), instrument="x",
                    action="INVALID", delta_weight=0, prev_weight=0,
                    new_weight=0, reason="")


def test_report_artifact_defaults():
    r = DailyReportArtifact(
        market_summary="", position_change_summary="",
        factor_summary="", coverage_summary={}, stability_summary={},
        artifact_refs={},
    )
    assert r.risk_flags == []
    assert r.disclaimer == "本報告僅供研究，非投資建議"


def test_run_manifest_required_fields():
    m = RunManifest(
        run_id="r1", trade_date=date(2026, 4, 21), mode="daily",
        data_snapshot_id="s1", feature_set_id="v1", model_id="m1",
        git_commit="abc", started_at=datetime(2026, 4, 21, 14, 0),
        status="success",
    )
    assert m.schema_version == "v1"
    assert m.artifact_uris == {}
    d = json.loads(m.model_dump_json())
    for field in ("run_id", "trade_date", "mode", "git_commit", "status"):
        assert field in d


def test_run_manifest_valid_modes():
    for mode in ("daily", "backfill", "retrain"):
        m = RunManifest(
            run_id="r1", trade_date=date(2026, 4, 21), mode=mode,
            data_snapshot_id="s1", feature_set_id="v1", model_id="m1",
            git_commit="abc", started_at=datetime(2026, 4, 21, 14, 0),
            status="running",
        )
        assert m.mode == mode
