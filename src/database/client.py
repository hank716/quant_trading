"""Supabase client wrapper with mock fallback."""
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SupabaseClient:
    """Thin Supabase wrapper. No credentials → mock mode (in-memory)."""

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        self.url = url or os.getenv("SUPABASE_URL", "")
        self.key = key or os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
        self.mock_mode = not (self.url and self.key)
        self._mock_store: dict[str, list[dict]] = {}
        self._client = None

        if self.mock_mode:
            logger.warning("SupabaseClient: running in MOCK mode (no credentials)")
        else:
            try:
                from supabase import create_client
                self._client = create_client(self.url, self.key)
            except Exception as exc:
                logger.error(f"Supabase init failed, falling back to mock: {exc}")
                self.mock_mode = True

    # ------------------------------------------------------------------ #
    # Core operations
    # ------------------------------------------------------------------ #

    def insert(self, table: str, rows: list[dict[str, Any]]) -> list[dict]:
        if not rows:
            return []
        if self.mock_mode:
            self._mock_store.setdefault(table, []).extend(rows)
            return rows
        result = self._client.table(table).insert(rows).execute()
        return result.data or []

    def update(self, table: str, match: dict[str, Any], values: dict[str, Any]) -> list[dict]:
        if self.mock_mode:
            updated = []
            for row in self._mock_store.get(table, []):
                if all(row.get(k) == v for k, v in match.items()):
                    row.update(values)
                    updated.append(row)
            return updated
        q = self._client.table(table).update(values)
        for k, v in match.items():
            q = q.eq(k, v)
        result = q.execute()
        return result.data or []

    def select(self, table: str, filters: Optional[dict[str, Any]] = None,
               limit: int = 100) -> list[dict]:
        if self.mock_mode:
            rows = self._mock_store.get(table, [])
            if filters:
                rows = [r for r in rows if all(r.get(k) == v for k, v in filters.items())]
            return rows[:limit]
        q = self._client.table(table).select("*").limit(limit)
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        result = q.execute()
        return result.data or []

    def select_latest(self, table: str, order_by: str, limit: int = 1) -> list[dict]:
        if self.mock_mode:
            rows = self._mock_store.get(table, [])
            try:
                rows = sorted(rows, key=lambda r: r.get(order_by, ""), reverse=True)
            except TypeError:
                pass
            return rows[:limit]
        result = (
            self._client.table(table)
            .select("*")
            .order(order_by, desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
