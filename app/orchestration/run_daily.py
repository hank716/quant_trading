"""Daily pipeline: sync → train/signal → select → explain → Discord → Supabase."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_profile(profile: str) -> dict:
    import yaml
    path = Path(f"config/profiles/{profile}.yaml")
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}")
    return yaml.safe_load(path.read_text())


def _sync_data(lookback_days: int = 5) -> None:
    from app.orchestration.sync_qlib_data import main as sync_main
    logger.info("Syncing Qlib data (lookback=%d days)…", lookback_days)
    sync_main(lookback_days=lookback_days)


def _run_training(workflow: str) -> str | None:
    """Run qrun workflow, return MLflow run_id or None."""
    from app.orchestration.run_training import run as train_run
    logger.info("Running training workflow: %s", workflow)
    rc = train_run(workflow)
    if rc != 0:
        logger.error("Training failed (exit code %d)", rc)
        return None
    try:
        import mlflow
        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "file:workspace/mlruns"))
        runs = mlflow.search_runs(order_by=["start_time DESC"], max_results=1)
        if not runs.empty:
            return runs.iloc[0]["run_id"]
    except Exception as exc:
        logger.warning("Could not retrieve MLflow run_id: %s", exc)
    return None


def _load_signal(run_id: str) -> "pd.DataFrame | None":
    """Load prediction signal from MLflow recorder."""
    try:
        from qlib.workflow import R
        from qlib_ext import init_tw_qlib
        init_tw_qlib()
        recorder = R.get_recorder(run_id=run_id, experiment_name="workflow")
        pred = recorder.load_object("pred.pkl")
        if pred is None:
            return None
        if hasattr(pred, "iloc"):
            import pandas as pd
            if isinstance(pred.index, pd.MultiIndex):
                latest_date = pred.index.get_level_values("datetime").max()
                pred = pred.xs(latest_date, level="datetime")
            if isinstance(pred, pd.DataFrame):
                pred = pred.iloc[:, 0]
        return pred
    except Exception as exc:
        logger.warning("Could not load signal from recorder %s: %s", run_id, exc)
        return None


def _select_candidates(signal: "pd.Series", profile_cfg: dict, top_k: int = 20) -> list[dict]:
    """Apply rule-based or LLM selector to score Series."""
    rows = [
        {"instrument": sym, "score": float(score), "metrics": {}}
        for sym, score in signal.nlargest(top_k * 3).items()
    ]
    provider = profile_cfg.get("selector_provider", "rule_based")
    try:
        from llm.selector import SelectorFactory
        SelectorFactory.build(provider)
        selected = rows[:top_k]
        logger.info("Selected %d candidates via %s", len(selected), provider)
        return selected
    except Exception as exc:
        logger.warning("Selector failed (%s), using top-%d by score: %s", provider, top_k, exc)
        return rows[:top_k]


def _explain_candidates(candidates: list[dict], profile_cfg: dict) -> list[dict]:
    """Add LLM/rule-based Chinese thesis to each candidate."""
    provider = profile_cfg.get("llm_provider", "rule_based")
    try:
        from llm.explainer import ExplainerFactory
        explainer = ExplainerFactory.build(provider)
        for c in candidates:
            payload = {"instrument": c["instrument"], "score": c["score"], "metrics": c.get("metrics", {})}
            c["thesis"] = explainer.explain(payload)
    except Exception as exc:
        logger.warning("Explainer failed: %s — skipping thesis", exc)
    return candidates


def _push_discord(candidates: list[dict], profile_cfg: dict, run_id: str | None, metrics: dict) -> None:
    from app.notify.discord_notifier import QlibDiscordNotifier, build_message
    discord_cfg = profile_cfg.get("discord", {})
    if not discord_cfg.get("enabled", False):
        logger.info("Discord disabled for this profile")
        return
    notifier = QlibDiscordNotifier(discord_cfg)
    msg = build_message(candidates=candidates, run_id=run_id, metrics=metrics, trade_date=date.today())
    notifier.send(msg)


def _register_supabase(run_id: str | None, status: str, metrics: dict) -> None:
    try:
        from src.database.client import SupabaseClient
        from src.database.qlib_crud import QlibRunCRUD
        client = SupabaseClient()
        crud = QlibRunCRUD(client)
        if run_id:
            crud.update_status(run_id, status, metrics)
        logger.info("Supabase qlib_runs updated: %s → %s", run_id, status)
    except Exception as exc:
        logger.warning("Supabase update skipped: %s", exc)


def run(profile: str, skip_sync: bool = False, skip_train: bool = False,
        workflow: str = "qlib_ext/workflows/daily_lgbm.yaml",
        top_k: int = 20) -> int:
    """Run the full daily Qlib pipeline and return exit code."""
    profile_cfg = _load_profile(profile)
    run_id = None
    metrics: dict = {}

    try:
        if not skip_sync:
            _sync_data(lookback_days=5)

        if not skip_train:
            run_id = _run_training(workflow)
            if run_id is None:
                logger.error("Training produced no run_id — aborting")
                return 1
            try:
                from app.control.mlflow_helper import get_run_metrics
                metrics = get_run_metrics(run_id)
            except Exception:
                pass

        signal = _load_signal(run_id) if run_id else None
        if signal is None or signal.empty:
            logger.warning("No signal available — using empty candidate list")
            candidates = []
        else:
            candidates = _select_candidates(signal, profile_cfg, top_k=top_k)
            candidates = _explain_candidates(candidates, profile_cfg)

        _push_discord(candidates, profile_cfg, run_id, metrics)
        _register_supabase(run_id, "success", metrics)
        logger.info("run_daily complete: run_id=%s candidates=%d", run_id, len(candidates))
        return 0

    except Exception as exc:
        logger.exception("run_daily failed: %s", exc)
        _register_supabase(run_id, "failed", {})
        return 1


def main() -> None:
    """CLI entry point for the daily Qlib pipeline."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Daily Qlib pipeline")
    parser.add_argument("--profile", default="user_a")
    parser.add_argument("--skip-sync", action="store_true")
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument("--workflow", default="qlib_ext/workflows/daily_lgbm.yaml")
    parser.add_argument("--top-k", type=int, default=20)
    args = parser.parse_args()
    sys.exit(run(args.profile, args.skip_sync, args.skip_train, args.workflow, args.top_k))


if __name__ == "__main__":
    main()
