"""Daily pipeline: sync → train/signal → select → explain → Discord → Supabase."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load env files for local runs; Docker injects vars via env_file.
_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env.local", override=False)
load_dotenv(_ROOT / ".env", override=False)  # backward-compat fallback


def _load_profile(profile: str) -> tuple[dict, dict, list[dict]]:
    """Return (profile_cfg, strategy_cfg, portfolio_snapshot) for the given profile."""
    import yaml

    profile_path = Path(f"config/profiles/{profile}.yaml")
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {profile_path}")
    profile_cfg = yaml.safe_load(profile_path.read_text()) or {}

    strategy_path = Path(profile_cfg.get("strategy", "config/strategy_1m.yaml"))
    strategy_cfg: dict = {}
    if strategy_path.exists():
        strategy_cfg = yaml.safe_load(strategy_path.read_text()) or {}
    else:
        logger.warning("Strategy file not found: %s; using empty config", strategy_path)

    try:
        from app.control.portfolio_editor import load_portfolio
        portfolio_snapshot = load_portfolio(profile)
    except Exception as exc:
        logger.warning("Could not load portfolio for profile %s: %s", profile, exc)
        portfolio_snapshot = []

    return profile_cfg, strategy_cfg, portfolio_snapshot


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
        runs = mlflow.search_runs(
            experiment_names=["workflow"],
            order_by=["start_time DESC"],
            max_results=1,
        )
        if not runs.empty:
            return runs.iloc[0]["run_id"]
    except Exception as exc:
        logger.warning("Could not retrieve MLflow run_id: %s", exc)
    return None


def _load_signal(run_id: str) -> "pd.Series | None":
    """Load prediction signal from MLflow recorder."""
    try:
        from qlib.workflow import R
        from qlib_ext import init_tw_qlib
        init_tw_qlib()
        recorder = R.get_recorder(recorder_id=run_id, experiment_name="workflow")
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


def _load_universe_meta() -> dict[str, dict]:
    """Best-effort ticker → {name, market, industry} lookup via FinMind stock info.

    Returns an empty dict on any failure — the LLM will still see ticker + score.
    """
    try:
        from datetime import date as _date

        from data.finmind_client import FinMindClient
        from core.universe import UniverseBuilder

        ub = UniverseBuilder(client=FinMindClient(), as_of_date=_date.today())
        catalog = ub.build()
        return {
            row.stock_id: {
                "name": row.stock_name,
                "market": row.market_type,
                "industry": row.industry_category or "",
            }
            for row in catalog
        }
    except Exception as exc:
        logger.debug("Universe metadata unavailable: %s", exc)
        return {}


def _select_and_explain(
    signal: "pd.Series",
    strategy_cfg: dict,
    profile_cfg: dict,
    portfolio_snapshot: list[dict],
) -> tuple[list[dict], str]:
    """Run selector + explainer; return (candidate list, thesis string)."""
    from app.llm.adapters import run_explanation, run_selection

    universe_meta = _load_universe_meta()
    selector_output = run_selection(signal, strategy_cfg, profile_cfg, portfolio_snapshot, universe_meta)
    thesis = run_explanation(selector_output, signal, strategy_cfg, profile_cfg, portfolio_snapshot)

    candidates: list[dict] = []
    for rank, sel in enumerate(selector_output.get("selections", []), start=1):
        candidates.append(
            {
                "rank": rank,
                "instrument": sel.get("asset"),
                "verdict": sel.get("verdict"),
                "confidence": sel.get("confidence"),
                "score": signal.get(sel.get("asset"), 0.0) if hasattr(signal, "get") else 0.0,
                "summary": sel.get("summary", ""),
                "bull_points": sel.get("bull_points", []),
                "bear_points": sel.get("bear_points", []),
                "invalidation_conditions": sel.get("invalidation_conditions", []),
                "thesis": "",
            }
        )
    # Attach full thesis to the first candidate (Discord shows it inline).
    if candidates and thesis:
        candidates[0]["thesis"] = thesis
    return candidates, thesis


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


def run(
    profile: str,
    skip_sync: bool = False,
    skip_train: bool = False,
    workflow: str = "qlib_ext/workflows/daily_lgbm.yaml",
    top_k: int = 20,
) -> int:
    """Run the full daily Qlib pipeline and return exit code."""
    del top_k  # top-K is derived from strategy_cfg decision.max_consider + max_watch
    profile_cfg, strategy_cfg, portfolio_snapshot = _load_profile(profile)
    run_id: str | None = None
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
            candidates: list[dict] = []
            thesis = ""
        else:
            candidates, thesis = _select_and_explain(signal, strategy_cfg, profile_cfg, portfolio_snapshot)

        _push_discord(candidates, profile_cfg, run_id, metrics)
        _register_supabase(run_id, "success", metrics)
        logger.info("run_daily complete: run_id=%s candidates=%d thesis_chars=%d",
                    run_id, len(candidates), len(thesis))
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
