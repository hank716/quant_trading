"""Champion model management via MLflow model stages."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_CHAMPION_TAG = "champion"
_CHAMPION_VALUE = "true"


def _client():
    import mlflow
    from app.control.mlflow_helper import _tracking_uri
    mlflow.set_tracking_uri(_tracking_uri())
    return mlflow.tracking.MlflowClient()


def get_champion(family: str) -> dict[str, Any] | None:
    """Return the run tagged as champion for the given family, or None."""
    import mlflow
    from app.control.mlflow_helper import _tracking_uri
    mlflow.set_tracking_uri(_tracking_uri())
    runs = mlflow.search_runs(
        filter_string=f"tags.family = '{family}' AND tags.{_CHAMPION_TAG} = '{_CHAMPION_VALUE}'",
        order_by=["start_time DESC"],
        max_results=1,
    )
    if runs.empty:
        return None
    row = runs.iloc[0]
    return {"run_id": row["run_id"], "metrics": {k[len("metrics."):]: v for k, v in row.items() if k.startswith("metrics.")}}


def promote(run_id: str, family: str, reason: str = "") -> None:
    """Tag run_id as champion, demote any previous champion in the same family."""
    client = _client()
    prev = get_champion(family)
    if prev and prev["run_id"] != run_id:
        client.delete_tag(prev["run_id"], _CHAMPION_TAG)
        logger.info("Demoted previous champion %s", prev["run_id"])
    client.set_tag(run_id, _CHAMPION_TAG, _CHAMPION_VALUE)
    client.set_tag(run_id, "family", family)
    if reason:
        client.set_tag(run_id, "promotion_reason", reason)
    logger.info("Promoted %s as champion for family=%s", run_id, family)


def list_candidates(family: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return recent runs for the given family, newest first."""
    import mlflow
    from app.control.mlflow_helper import _tracking_uri
    mlflow.set_tracking_uri(_tracking_uri())
    runs = mlflow.search_runs(
        filter_string=f"tags.family = '{family}'",
        order_by=["start_time DESC"],
        max_results=limit,
    )
    if runs.empty:
        return []
    result = []
    for _, row in runs.iterrows():
        metrics = {k[len("metrics."):]: v for k, v in row.items() if k.startswith("metrics.")}
        result.append({"run_id": row["run_id"], "metrics": metrics, "tags": {}})
    return result
