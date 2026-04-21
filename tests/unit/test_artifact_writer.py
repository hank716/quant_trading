import json
from datetime import date, datetime
from pathlib import Path

import pytest

from src.signals.schema import SignalRecord
from src.portfolio.schema import PositionRecord, TradeRecord
from src.reporting.schema import DailyReportArtifact, RunManifest
from src.storage.artifact_writer import (
    write_signals, write_positions, write_trades,
    write_report, write_manifest, upload_run_artifacts,
)


@pytest.fixture
def base(tmp_path):
    return tmp_path / "runs"


def _signal():
    return SignalRecord(trade_date=date(2026, 4, 21), instrument="2330", score=0.9,
                        model_id="rule_v1", data_snapshot_id="snap_001")


def _position():
    return PositionRecord(trade_date=date(2026, 4, 21), instrument="2330",
                          target_weight=0.1, notional=100000, score=0.9,
                          selection_reason="high score")


def _trade():
    return TradeRecord(trade_date=date(2026, 4, 21), instrument="2330",
                       action="BUY", delta_weight=0.1, prev_weight=0.0,
                       new_weight=0.1, reason="new entry")


def _report():
    return DailyReportArtifact(
        market_summary="平盤", position_change_summary="新增 1 檔",
        factor_summary="動能強", coverage_summary={}, stability_summary={},
        artifact_refs={"signals": "signals.json"},
    )


def _manifest(run_id):
    return RunManifest(
        run_id=run_id, trade_date=date(2026, 4, 21), mode="daily",
        data_snapshot_id="snap_001", feature_set_id="v1", model_id="rule_v1",
        git_commit="abc1234", started_at=datetime(2026, 4, 21, 14, 0),
        status="success",
    )


def test_write_signals(base):
    path = write_signals("run_001", [_signal()], base)
    assert path.exists()
    data = json.loads(path.read_text())
    assert len(data) == 1
    assert data[0]["instrument"] == "2330"


def test_write_positions(base):
    path = write_positions("run_001", [_position()], base)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data[0]["target_weight"] == 0.1


def test_write_trades(base):
    path = write_trades("run_001", [_trade()], base)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data[0]["action"] == "BUY"


def test_write_report(base):
    path = write_report("run_001", _report(), base)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["disclaimer"] == "本報告僅供研究，非投資建議"


def test_write_manifest(base):
    path = write_manifest("run_001", _manifest("run_001"), base)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["status"] == "success"
    assert data["run_id"] == "run_001"


def test_all_five_files_written(base):
    run_id = "run_all"
    write_signals(run_id, [_signal()], base)
    write_positions(run_id, [_position()], base)
    write_trades(run_id, [_trade()], base)
    write_report(run_id, _report(), base)
    write_manifest(run_id, _manifest(run_id), base)
    files = {f.name for f in (base / run_id).iterdir()}
    assert files == {"signals.json", "positions.json", "trades.json", "report.json", "manifest.json"}


def test_upload_run_artifacts_mock(base, monkeypatch):
    run_id = "run_upload"
    write_signals(run_id, [_signal()], base)
    write_manifest(run_id, _manifest(run_id), base)

    uploaded = []

    class MockCloud:
        def mkdir(self, p): pass
        def upload_file(self, local, remote):
            uploaded.append(remote)
            return {"mock": True}

    uris = upload_run_artifacts(run_id, date(2026, 4, 21), MockCloud(), base)
    assert any("signals.json" in u for u in uploaded)
    assert len(uris) > 0
