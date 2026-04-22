"""CRUD operations for qlib_runs table."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class QlibRunCRUD:
    def __init__(self, client: Any) -> None:
        self._client = client

    def register(
        self,
        mlflow_run_id: str,
        experiment_name: str = "",
        family: str = "",
        workflow_config: str = "",
        status: str = "running",
        metrics: dict | None = None,
    ) -> dict:
        """Insert a new qlib_runs row; return the created record."""
        row = {
            "mlflow_run_id": mlflow_run_id,
            "experiment_name": experiment_name,
            "family": family,
            "workflow_config": workflow_config,
            "status": status,
            "metrics": metrics or {},
        }
        result = self._client.insert("qlib_runs", [row])
        return result[0] if result else {}

    def update_status(self, mlflow_run_id: str, status: str, metrics: dict | None = None) -> dict:
        """Update status (and optionally metrics) for an existing run."""
        update: dict[str, Any] = {"status": status}
        if metrics is not None:
            update["metrics"] = metrics
        result = self._client.update("qlib_runs", {"mlflow_run_id": mlflow_run_id}, update)
        return result[0] if result else {}

    def get_by_run_id(self, mlflow_run_id: str) -> dict | None:
        """Return the qlib_runs row for the given mlflow_run_id, or None."""
        return self._client.select_one("qlib_runs", {"mlflow_run_id": mlflow_run_id})

    def list_by_family(self, family: str, limit: int = 20) -> list[dict]:
        """Return recent runs for a model family, newest first."""
        return self._client.select(
            "qlib_runs",
            filters={"family": family},
            order="created_at.desc",
            limit=limit,
        )
