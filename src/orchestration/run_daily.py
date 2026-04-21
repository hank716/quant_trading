"""Daily pipeline orchestrator - delegates to main.py and writes artifacts."""
import sys
import uuid
from datetime import datetime
from pathlib import Path


def _run_with_artifacts(argv=None):
    """Run main pipeline and write artifact files to workspace/runs/{run_id}/."""
    import os
    from datetime import date

    # Import the existing main pipeline
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import main as _main

    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    started_at = datetime.now()

    # Parse args and run the existing pipeline
    args = _main.parse_args()
    result = _main.run_pipeline(args) if hasattr(_main, "run_pipeline") else None

    if result is None:
        # Fallback: just execute main() as-is
        _main.main()
        return

    # Write artifacts
    from src.reporting.converter import (
        daily_result_to_signals, daily_result_to_positions,
        daily_result_to_trades, daily_result_to_report, build_manifest,
    )
    from src.storage.artifact_writer import (
        write_signals, write_positions, write_trades,
        write_report, write_manifest,
    )
    from src.storage.pcloud_client import PCloudClient

    cache_base = Path(os.getenv("CACHE_DIR", "workspace/hotdata")).parent
    base = cache_base / "runs"

    signals = daily_result_to_signals(result, data_snapshot_id=result.date)
    positions = daily_result_to_positions(result)
    trades = daily_result_to_trades(result, [])
    report_artifact = daily_result_to_report(result, {})
    manifest = build_manifest(run_id, date.fromisoformat(result.date), result, {}, started_at)

    write_signals(run_id, signals, base)
    write_positions(run_id, positions, base)
    write_trades(run_id, trades, base)
    write_report(run_id, report_artifact, base)
    write_manifest(run_id, manifest, base)

    print(f"Artifacts written to {base / run_id}")


if __name__ == "__main__":
    _run_with_artifacts()
