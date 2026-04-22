"""Daily pipeline orchestrator - delegates to main.py and writes artifacts + DB."""
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd


def _run_with_artifacts(argv=None):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import main as _main

    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    started_at = datetime.now()

    args = _main.parse_args()
    result = _main.run_pipeline(args) if hasattr(_main, "run_pipeline") else None

    if result is None:
        _main.main()
        return

    from datetime import date as _date
    from src.reporting.converter import (
        daily_result_to_signals, daily_result_to_positions,
        daily_result_to_trades, daily_result_to_report, build_manifest,
        _git_commit,
    )
    from src.storage.artifact_writer import (
        write_signals, write_positions, write_trades,
        write_report, write_manifest,
    )
    from src.storage.pcloud_client import PCloudClient
    from src.database.client import SupabaseClient
    from src.database.crud import PipelineRunCRUD, ArtifactCRUD, CandidateCRUD

    cache_base = Path(os.getenv("CACHE_DIR", "workspace/hotdata")).parent
    base = cache_base / "runs"
    trade_date = _date.fromisoformat(result.date)

    # --- Supabase: start run ---
    db = SupabaseClient()
    run_crud = PipelineRunCRUD(db)
    artifact_crud = ArtifactCRUD(db)
    candidate_crud = CandidateCRUD(db)
    run_crud.start(run_id, trade_date, git_commit=_git_commit())

    # --- Write local artifacts ---
    signals = daily_result_to_signals(result, data_snapshot_id=result.date)
    positions = daily_result_to_positions(result)
    trades = daily_result_to_trades(result, [])

    p_signals = write_signals(run_id, signals, base)
    p_positions = write_positions(run_id, positions, base)
    p_trades = write_trades(run_id, trades, base)

    artifact_uris = {
        "signals": str(p_signals),
        "positions": str(p_positions),
        "trades": str(p_trades),
    }

    report_artifact = daily_result_to_report(result, artifact_uris)
    manifest = build_manifest(run_id, trade_date, result, artifact_uris, started_at)
    p_report = write_report(run_id, report_artifact, base)
    p_manifest = write_manifest(run_id, manifest, base)
    artifact_uris["report"] = str(p_report)
    artifact_uris["manifest"] = str(p_manifest)

    # --- Supabase: register artifacts ---
    for name, uri in artifact_uris.items():
        artifact_crud.register(run_id, name, uri)

    # --- Supabase: insert candidates ---
    candidate_rows = [
        {"instrument": c.asset, "list_type": "eligible", "score": c.score,
         "selection_reason": "; ".join(c.why[:2])}
        for c in result.eligible_candidates
    ] + [
        {"instrument": c.asset, "list_type": "watch", "score": c.score}
        for c in result.watch_only_candidates
    ]
    candidate_crud.bulk_insert(run_id, trade_date, candidate_rows)

    # --- Coverage check (proxy from DailyResult) ---
    try:
        import json as _json
        import re as _re
        from src.monitoring.coverage_checker import build_coverage_snapshot
        from src.registry.retrain_gate import build_retrain_decision
        from src.database.crud import CoverageCRUD

        # Extract scanned universe size from notes written by main.py
        universe_size = 0
        for note in (result.notes or []):
            m = _re.search(r"掃描股票數.*?(\d+)", note)
            if m:
                universe_size = int(m.group(1))
                break

        # Proxy: assume stocks with any signal result have revenue data
        # Financial coverage: notes tell us how many financial rows were cached
        rev_covered = universe_size  # conservative — real check requires re-fetch
        fin_match = next(
            (_re.search(r"財報資料.*?(\d+)\s*筆", n) for n in (result.notes or []) if "財報" in n),
            None,
        )
        fin_covered = int(fin_match.group(1)) if fin_match else 0

        rev_cov_pct = round(rev_covered / universe_size, 4) if universe_size else 0.0
        fin_cov_pct = round(min(fin_covered / universe_size, 1.0), 4) if universe_size else 0.0
        missing_crit = [
            c.asset for c in result.eligible_candidates
            if not any(c.asset in n for n in (result.notes or []))
        ]

        snap = build_coverage_snapshot(
            trade_date,
            {"coverage_pct": rev_cov_pct, "covered": rev_covered, "total": universe_size},
            {"coverage_pct": fin_cov_pct, "covered": fin_covered, "total": universe_size},
            missing_crit,
        )
        retrain = build_retrain_decision(snap, last_retrain_date=None, today=trade_date)

        snap_path = base / run_id / "coverage_snapshot.json"
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text(_json.dumps(snap, ensure_ascii=False, indent=2))

        retrain_path = base / run_id / "retrain_decision.json"
        retrain_path.write_text(_json.dumps(retrain, ensure_ascii=False, indent=2))

        artifact_uris["coverage_snapshot"] = str(snap_path)
        artifact_uris["retrain_decision"] = str(retrain_path)

        CoverageCRUD(db).insert_snapshot(
            trade_date=trade_date,
            run_id=run_id,
            revenue_coverage=rev_cov_pct,
            financial_coverage=fin_cov_pct,
            missing_critical=missing_crit,
        )
        artifact_crud.register(run_id, "coverage_snapshot", str(snap_path))
        artifact_crud.register(run_id, "retrain_decision", str(retrain_path))
        print(f"Coverage: revenue={rev_cov_pct:.1%} financial={fin_cov_pct:.1%}")
        if retrain["should_retrain"]:
            print(f"Retrain gate: TRIGGER — {retrain['reason']}")
    except Exception as _cov_exc:
        print(f"Coverage check skipped: {_cov_exc}")

    # --- ML scoring + SHAP (champion model, optional) ---
    try:
        from src.registry.model_registry import ModelRegistry
        from src.signals.predictor import predict_from_champion
        from src.signals.explainer_shap import compute_shap_summary, write_shap_summary

        registry = ModelRegistry(db=db)
        champion = registry.get_champion("lgbm_binary")

        # real feature matrix wiring comes after Phase 5d full integration
        _feature_matrix_placeholder = pd.DataFrame()

        ml_scores = predict_from_champion(
            _feature_matrix_placeholder,
            family="lgbm_binary",
            registry=registry,
            cache_dir=base / "models",
        )
        if ml_scores is not None:
            print(f"ML scoring: {len(ml_scores)} instruments scored by champion model")

            # SHAP summary (only when we have features + model)
            if champion and not _feature_matrix_placeholder.empty:
                import joblib as _joblib
                model_path = registry.download_model(champion["model_id"], base / "models")
                _model = _joblib.load(model_path)
                shap_summary = compute_shap_summary(_model, _feature_matrix_placeholder)
                shap_path = write_shap_summary(shap_summary, run_id, output_dir=base)
                artifact_uris["shap_summary"] = str(shap_path)
                artifact_crud.register(run_id, "shap_summary", str(shap_path))

                # upload SHAP to pCloud
                pcloud = PCloudClient()
                remote_shap = f"/shap/date={trade_date.isoformat()}/run_id={run_id}/shap_summary.json"
                pcloud.upload_file(shap_path, remote_shap)
                print(f"SHAP summary: top features written to {shap_path}")
    except Exception as _ml_exc:
        print(f"ML scoring/SHAP skipped: {_ml_exc}")

    # --- Supabase: finish run ---
    run_crud.finish(run_id, status="success")

    print(f"run_id: {run_id}")
    print(f"Artifacts: {base / run_id}")


if __name__ == "__main__":
    _run_with_artifacts()
