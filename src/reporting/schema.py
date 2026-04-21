from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel


class DailyReportArtifact(BaseModel):
    market_summary: str
    position_change_summary: str
    factor_summary: str
    coverage_summary: dict
    stability_summary: dict
    risk_flags: list[str] = []
    artifact_refs: dict[str, str]
    disclaimer: str = "本報告僅供研究，非投資建議"


class RunManifest(BaseModel):
    run_id: str
    trade_date: date
    mode: Literal["daily", "backfill", "retrain"]
    data_snapshot_id: str
    feature_set_id: str
    model_id: str
    schema_version: str = "v1"
    prompt_version: Optional[str] = None
    git_commit: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: Literal["running", "success", "failed", "partial"]
    artifact_uris: dict[str, str] = {}
