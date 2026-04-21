"""High-level CRUD helpers built on SupabaseClient."""
from datetime import date, datetime
from typing import Optional

from src.database.client import SupabaseClient


class PipelineRunCRUD:
    def __init__(self, client: SupabaseClient):
        self._db = client

    def start(self, run_id: str, trade_date: date, mode: str = "daily",
              git_commit: str = "") -> dict:
        row = {
            "run_id": run_id,
            "trade_date": trade_date.isoformat(),
            "mode": mode,
            "status": "running",
            "git_commit": git_commit,
            "started_at": datetime.now().isoformat(),
        }
        rows = self._db.insert("pipeline_runs", [row])
        return rows[0] if rows else row

    def finish(self, run_id: str, status: str = "success",
               notes: Optional[str] = None) -> dict:
        values = {"status": status, "ended_at": datetime.now().isoformat()}
        if notes:
            values["notes"] = notes
        rows = self._db.update("pipeline_runs", {"run_id": run_id}, values)
        return rows[0] if rows else {"run_id": run_id, "status": status}

    def latest(self, limit: int = 20) -> list[dict]:
        return self._db.select_latest("pipeline_runs", "started_at", limit=limit)


class ArtifactCRUD:
    def __init__(self, client: SupabaseClient):
        self._db = client

    def register(self, run_id: str, artifact: str, uri: str) -> dict:
        row = {"run_id": run_id, "artifact": artifact, "uri": uri}
        rows = self._db.insert("run_artifacts", [row])
        return rows[0] if rows else row


class CandidateCRUD:
    def __init__(self, client: SupabaseClient):
        self._db = client

    def bulk_insert(self, run_id: str, trade_date: date,
                    candidates: list[dict]) -> list[dict]:
        rows = [
            {
                "run_id": run_id,
                "trade_date": trade_date.isoformat(),
                "instrument": c["instrument"],
                "list_type": c.get("list_type", "eligible"),
                "score": c.get("score"),
                "selection_reason": c.get("selection_reason", ""),
                "metrics": c.get("metrics", {}),
            }
            for c in candidates
        ]
        return self._db.insert("daily_candidates", rows)

    def latest_by_date(self, trade_date: date) -> list[dict]:
        return self._db.select("daily_candidates", {"trade_date": trade_date.isoformat()})


class CoverageCRUD:
    def __init__(self, client: SupabaseClient):
        self._db = client

    def insert_snapshot(self, trade_date: date, run_id: str,
                        revenue_coverage: float, financial_coverage: float,
                        missing_critical: list) -> dict:
        row = {
            "trade_date": trade_date.isoformat(),
            "run_id": run_id,
            "revenue_coverage": revenue_coverage,
            "financial_coverage": financial_coverage,
            "missing_critical": missing_critical,
        }
        rows = self._db.insert("coverage_snapshots", [row])
        return rows[0] if rows else row

    def latest(self, limit: int = 30) -> list[dict]:
        return self._db.select_latest("coverage_snapshots", "trade_date", limit=limit)
