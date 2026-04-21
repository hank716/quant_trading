"""Writes run artifacts to workspace/runs/{run_id}/"""
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.signals.schema import SignalRecord
from src.portfolio.schema import PositionRecord, TradeRecord
from src.reporting.schema import DailyReportArtifact, RunManifest


def _runs_dir() -> Path:
    base = Path(os.getenv("CACHE_DIR", "workspace/hotdata")).parent
    return base / "runs"


def run_dir(run_id: str, base: Path | None = None) -> Path:
    root = base if base is not None else _runs_dir()
    return root / run_id


def write_signals(run_id: str, records: list[SignalRecord], base: Path | None = None) -> Path:
    out = run_dir(run_id, base) / "signals.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([r.model_dump(mode="json") for r in records], ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def write_positions(run_id: str, records: list[PositionRecord], base: Path | None = None) -> Path:
    out = run_dir(run_id, base) / "positions.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([r.model_dump(mode="json") for r in records], ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def write_trades(run_id: str, records: list[TradeRecord], base: Path | None = None) -> Path:
    out = run_dir(run_id, base) / "trades.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([r.model_dump(mode="json") for r in records], ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def write_report(run_id: str, artifact: DailyReportArtifact, base: Path | None = None) -> Path:
    out = run_dir(run_id, base) / "report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
    return out


def write_manifest(run_id: str, manifest: RunManifest, base: Path | None = None) -> Path:
    out = run_dir(run_id, base) / "manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return out


def upload_run_artifacts(run_id: str, trade_date: date, pcloud_client: Any, base: Path | None = None) -> dict[str, str]:
    """Upload all files in run_dir to pCloud. Returns {filename: remote_path}."""
    src_dir = run_dir(run_id, base)
    date_str = trade_date.isoformat()
    remote_base = f"/reports/date={date_str}/run_id={run_id}"
    pcloud_client.mkdir(remote_base)

    uris: dict[str, str] = {}
    for f in sorted(src_dir.iterdir()):
        if f.is_file():
            remote_path = f"{remote_base}/{f.name}"
            pcloud_client.upload_file(f, remote_path)
            uris[f.name] = remote_path

    manifest_remote = f"/manifests/date={date_str}/run_id={run_id}/manifest.json"
    manifest_local = src_dir / "manifest.json"
    if manifest_local.exists():
        pcloud_client.mkdir(f"/manifests/date={date_str}/run_id={run_id}")
        pcloud_client.upload_file(manifest_local, manifest_remote)
        uris["manifest_uri"] = manifest_remote

    return uris
