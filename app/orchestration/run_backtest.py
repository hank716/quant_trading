"""CLI: run Qlib backtest on an existing signal (MLflow run or score CSV)."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def run_from_mlflow(run_id: str, config_path: str) -> int:
    """Re-run only PortAnaRecord on an existing MLflow recorder."""
    import yaml
    from qlib_ext import init_tw_qlib

    init_tw_qlib()

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    port_cfg = cfg.get("port_analysis_config", {})
    if not port_cfg:
        logger.error("port_analysis_config not found in %s", config_path)
        return 1

    try:
        from qlib.workflow import R
        from qlib.workflow.record_temp import PortAnaRecord

        R.get_exp(experiment_name="workflow")
        recorder = R.get_recorder(run_id=run_id, experiment_name="workflow")
        rec = PortAnaRecord(recorder=recorder, config=port_cfg)
        rec.generate()
        logger.info("PortAnaRecord generated for run %s", run_id)
        return 0
    except Exception as exc:
        logger.error("Backtest failed: %s", exc)
        return 1


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Run Qlib backtest")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--mlflow-run-id", help="Existing MLflow run_id")
    grp.add_argument("--score-csv", help="Score CSV for ad-hoc backtest")
    parser.add_argument(
        "--workflow",
        default="qlib_ext/workflows/daily_lgbm.yaml",
        help="Workflow YAML (for port_analysis_config)",
    )
    args = parser.parse_args()

    if args.mlflow_run_id:
        sys.exit(run_from_mlflow(args.mlflow_run_id, args.workflow))
    else:
        logger.error("--score-csv backtest not yet implemented")
        sys.exit(1)


if __name__ == "__main__":
    main()
