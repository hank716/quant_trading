"""MLflow helper for fin — list experiments, retrieve recorder metrics."""
import os
from typing import Any

import mlflow


def _tracking_uri() -> str:
    return os.environ.get("MLFLOW_TRACKING_URI", "file:workspace/mlruns")


def list_experiments() -> list[dict[str, Any]]:
    """Return list of {experiment_id, name, lifecycle_stage} dicts."""
    mlflow.set_tracking_uri(_tracking_uri())
    return [
        {"experiment_id": e.experiment_id, "name": e.name, "lifecycle_stage": e.lifecycle_stage}
        for e in mlflow.search_experiments()
    ]


def get_run_metrics(run_id: str) -> dict[str, float]:
    """Return the metrics dict for a given MLflow run_id."""
    mlflow.set_tracking_uri(_tracking_uri())
    run = mlflow.get_run(run_id)
    return dict(run.data.metrics)


def get_recorder(run_id: str) -> Any:
    """Return a loaded Qlib recorder for the given MLflow run_id."""
    from qlib.workflow import R
    recorder = R.get_recorder(run_id=run_id, recorder_name=None)
    return recorder
