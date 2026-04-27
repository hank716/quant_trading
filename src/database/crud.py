"""High-level CRUD helpers built on SupabaseClient.

Only tables that exist in the post-Phase-11 schema are kept:
- coverage_snapshots → CoverageCRUD
"""
from datetime import date
from typing import Optional

from src.database.client import SupabaseClient


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
