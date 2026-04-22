"""Training entry point: runs a qrun YAML workflow, registers result in Supabase."""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_WORKFLOW = "qlib_ext/workflows/daily_lgbm.yaml"


def _find_latest_mlflow_run(experiment_name: str = "workflow") -> str | None:
    """Return the most recent MLflow run_id for the given experiment."""
    try:
        import mlflow
        mlflow.set_tracking_uri(_mlflow_uri())
        runs = mlflow.search_runs(
            experiment_names=[experiment_name],
            order_by=["start_time DESC"],
            max_results=1,
        )
        if runs.empty:
            return None
        return runs.iloc[0]["run_id"]
    except Exception as exc:
        logger.warning("Could not retrieve MLflow run: %s", exc)
        return None


def _mlflow_uri() -> str:
    import os
    return os.environ.get("MLFLOW_TRACKING_URI", "file:workspace/mlruns")


def _register_in_supabase(
    mlflow_run_id: str,
    workflow_config: str,
    status: str,
    metrics: dict,
) -> None:
    try:
        from src.database.client import SupabaseClient
        from src.database.qlib_crud import QlibRunCRUD

        client = SupabaseClient()
        crud = QlibRunCRUD(client)
        crud.register(
            mlflow_run_id=mlflow_run_id,
            experiment_name="workflow",
            family="lgbm_binary_tw",
            workflow_config=workflow_config,
            status=status,
            metrics=metrics,
        )
        logger.info("Registered run %s in Supabase qlib_runs", mlflow_run_id)
    except Exception as exc:
        logger.warning("Supabase registration skipped: %s", exc)


def run(workflow: str) -> int:
    """Execute qrun workflow and register result. Returns exit code."""
    workflow_path = Path(workflow)
    if not workflow_path.exists():
        logger.error("Workflow file not found: %s", workflow)
        return 1

    logger.info("Starting qrun workflow: %s", workflow)
    result = subprocess.run(
        [sys.executable, "-m", "qlib.workflow.cli", workflow],
        capture_output=False,
    )

    status = "success" if result.returncode == 0 else "failed"
    run_id = _find_latest_mlflow_run()

    if run_id:
        from app.control.mlflow_helper import get_run_metrics
        try:
            metrics = get_run_metrics(run_id)
        except Exception:
            metrics = {}
        _register_in_supabase(run_id, workflow, status, metrics)
    else:
        logger.warning("No MLflow run_id found after qrun; skipping Supabase registration")

    return result.returncode


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Run Qlib training workflow")
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW, help="Path to qrun YAML")
    args = parser.parse_args()
    sys.exit(run(args.workflow))


if __name__ == "__main__":
    main()
