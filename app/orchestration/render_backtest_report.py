"""Render backtest report from an MLflow qrun recorder."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_recorder(run_id: str):
    from qlib.workflow import R
    from qlib_ext import init_tw_qlib
    init_tw_qlib()
    R.get_exp(experiment_name="workflow")
    return R.get_recorder(run_id=run_id, experiment_name="workflow")


def _extract_metrics(recorder) -> dict:
    """Extract IC, Rank IC, Sharpe, MDD, Turnover from recorder artifacts."""
    import pandas as pd

    metrics = {}
    try:
        sig_analysis = recorder.load_object("sig_analysis")
        if sig_analysis is not None:
            if hasattr(sig_analysis, "loc"):
                for key in ["IC", "ICIR", "Rank IC", "Rank ICIR"]:
                    if key in sig_analysis.index:
                        metrics[key] = float(sig_analysis.loc[key, "risk"])
    except Exception as exc:
        logger.debug("sig_analysis load failed: %s", exc)

    try:
        report_normal = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
        if report_normal is not None and not report_normal.empty:
            rets = report_normal.get("return", pd.Series(dtype=float))
            if len(rets) > 1:
                import numpy as np
                ann = 252
                metrics["Sharpe"] = float(rets.mean() / rets.std() * (ann ** 0.5)) if rets.std() > 0 else 0.0
                cum = (1 + rets).cumprod()
                roll_max = cum.cummax()
                drawdown = (cum - roll_max) / roll_max
                metrics["MDD"] = float(drawdown.min())
                metrics["Turnover"] = float(report_normal.get("turnover", pd.Series([0])).mean())
    except Exception as exc:
        logger.debug("report_normal load failed: %s", exc)

    return metrics


def _render_png(recorder, output_dir: Path) -> Path | None:
    """Generate cumulative-return chart using matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import pandas as pd

        report = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
        if report is None or report.empty:
            return None

        rets = report.get("return", pd.Series(dtype=float))
        excess = report.get("excess_return_without_cost", rets)
        cum_ret = (1 + rets).cumprod()
        cum_excess = (1 + excess).cumprod()

        fig, axes = plt.subplots(2, 1, figsize=(12, 8))
        axes[0].plot(cum_ret.index, cum_ret.values, label="Strategy", linewidth=1.2)
        axes[0].plot(cum_excess.index, cum_excess.values, label="Excess", linewidth=1.0, linestyle="--")
        axes[0].axhline(1.0, color="gray", linewidth=0.5)
        axes[0].set_title("Cumulative Return")
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        turnover = report.get("turnover", pd.Series(dtype=float))
        axes[1].bar(turnover.index, turnover.values, width=1.0, alpha=0.6)
        axes[1].set_title("Daily Turnover")
        axes[1].grid(True, alpha=0.3)

        plt.tight_layout()
        png_path = output_dir / "backtest_report.png"
        plt.savefig(png_path, dpi=120, bbox_inches="tight")
        plt.close()
        return png_path
    except Exception as exc:
        logger.warning("PNG rendering failed: %s", exc)
        return None


def upload_to_pcloud(run_id: str, output_dir: Path, date_str: str) -> None:
    """Upload backtest/ dir to pCloud at /backtest/date={date_str}/mlflow_run_id={run_id}/."""
    try:
        from src.storage.pcloud_client import PCloudClient
        client = PCloudClient()
        remote_base = f"/backtest/date={date_str}/mlflow_run_id={run_id}"
        client.mkdir(remote_base)
        for file_path in output_dir.iterdir():
            if file_path.is_file():
                client.upload_file(file_path, f"{remote_base}/{file_path.name}")
        logger.info("Uploaded backtest artifacts to pCloud: %s", remote_base)
    except Exception as exc:
        logger.warning("pCloud upload skipped: %s", exc)


def render(run_id: str, output_root: str = "workspace/runs") -> dict:
    """Render backtest report for the given MLflow run_id."""
    import pandas as pd  # noqa: F401 — imported for side-effects in helpers
    from datetime import date

    output_dir = Path(output_root) / run_id / "backtest"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        recorder = _load_recorder(run_id)
    except Exception as exc:
        logger.error("Could not load recorder for %s: %s", run_id, exc)
        return {}

    metrics = _extract_metrics(recorder)
    png_path = _render_png(recorder, output_dir)

    report = {
        "run_id": run_id,
        "metrics": metrics,
        "artifacts": {
            "png": str(png_path) if png_path else None,
        },
    }
    (output_dir / "backtest_metrics.json").write_text(json.dumps(report, indent=2))
    logger.info("Backtest report written to %s — metrics: %s", output_dir, metrics)

    date_str = date.today().isoformat()
    upload_to_pcloud(run_id, output_dir, date_str)

    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Render Qlib backtest report")
    parser.add_argument("--mlflow-run-id", required=True)
    parser.add_argument("--output-root", default="workspace/runs")
    args = parser.parse_args()
    result = render(args.mlflow_run_id, args.output_root)
    if not result:
        sys.exit(1)


if __name__ == "__main__":
    main()
