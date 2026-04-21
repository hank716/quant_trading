"""Daily pipeline orchestrator - delegates to main.py and writes artifacts + DB."""
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path


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

    # --- Supabase: finish run ---
    run_crud.finish(run_id, status="success")

    print(f"run_id: {run_id}")
    print(f"Artifacts: {base / run_id}")


if __name__ == "__main__":
    _run_with_artifacts()
