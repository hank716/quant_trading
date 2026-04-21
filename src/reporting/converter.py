"""Convert DailyResult to artifact schemas."""
import subprocess
from datetime import date, datetime

from core.models import DailyResult, Candidate
from src.signals.schema import SignalRecord
from src.portfolio.schema import PositionRecord, TradeRecord
from src.reporting.schema import DailyReportArtifact, RunManifest


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def daily_result_to_signals(result: DailyResult, model_id: str = "rule_v1",
                             data_snapshot_id: str = "") -> list[SignalRecord]:
    trade_date = date.fromisoformat(result.date)
    records = []
    for i, c in enumerate(result.eligible_candidates):
        records.append(SignalRecord(
            trade_date=trade_date,
            instrument=c.asset,
            score=c.score,
            model_id=model_id,
            data_snapshot_id=data_snapshot_id,
        ))
    for c in result.watch_only_candidates:
        records.append(SignalRecord(
            trade_date=trade_date,
            instrument=c.asset,
            score=c.score * 0.5,
            model_id=model_id,
            data_snapshot_id=data_snapshot_id,
        ))
    return records


def daily_result_to_positions(result: DailyResult) -> list[PositionRecord]:
    trade_date = date.fromisoformat(result.date)
    n = len(result.eligible_candidates)
    weight = round(1.0 / n, 4) if n > 0 else 0.0
    return [
        PositionRecord(
            trade_date=trade_date,
            instrument=c.asset,
            target_weight=weight,
            notional=0.0,
            score=c.score,
            selection_reason="; ".join(c.why[:2]) if c.why else "",
        )
        for c in result.eligible_candidates
    ]


def daily_result_to_trades(result: DailyResult,
                            prev_positions: list[PositionRecord]) -> list[TradeRecord]:
    trade_date = date.fromisoformat(result.date)
    prev_map = {p.instrument: p.target_weight for p in prev_positions}
    current = {p.instrument: p.target_weight for p in daily_result_to_positions(result)}

    all_ids = set(prev_map) | set(current)
    trades = []
    for inst in all_ids:
        prev_w = prev_map.get(inst, 0.0)
        new_w = current.get(inst, 0.0)
        delta = round(new_w - prev_w, 4)
        if delta > 0:
            action = "BUY"
        elif delta < 0:
            action = "SELL"
        else:
            action = "HOLD"
        trades.append(TradeRecord(
            trade_date=trade_date,
            instrument=inst,
            action=action,
            delta_weight=delta,
            prev_weight=prev_w,
            new_weight=new_w,
            reason="daily rebalance",
        ))
    return trades


def daily_result_to_report(result: DailyResult,
                            artifact_uris: dict[str, str]) -> DailyReportArtifact:
    eligible = [c.asset for c in result.eligible_candidates]
    watch = [c.asset for c in result.watch_only_candidates]
    return DailyReportArtifact(
        market_summary=f"action={result.action}",
        position_change_summary=f"consider={len(eligible)} watch={len(watch)}",
        factor_summary="; ".join(result.notes[-3:]) if result.notes else "",
        coverage_summary={},
        stability_summary={},
        artifact_refs=artifact_uris,
    )


def build_manifest(run_id: str, trade_date: date, result: DailyResult,
                   artifact_uris: dict[str, str],
                   started_at: datetime | None = None) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        trade_date=trade_date,
        mode="daily",
        data_snapshot_id=result.date,
        feature_set_id="v1",
        model_id=result.selection_mode or "rule_v1",
        git_commit=_git_commit(),
        started_at=started_at or datetime.now(),
        ended_at=datetime.now(),
        status="success",
        artifact_uris=artifact_uris,
    )
