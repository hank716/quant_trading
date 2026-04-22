"""Integration smoke test: run quick_debug workflow if qlib data is available."""
import os
import subprocess
import sys
from pathlib import Path
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not Path("workspace/qlib_data").exists(),
    reason="workspace/qlib_data not available — skipping qrun smoke test",
)
def test_qrun_quick_debug_exits_cleanly(tmp_path):
    """Run quick_debug workflow; check it exits without error."""
    env = {**os.environ, "MLFLOW_TRACKING_URI": f"file:{tmp_path}/mlruns"}
    result = subprocess.run(
        [sys.executable, "-m", "qlib.workflow.cli", "qlib_ext/workflows/quick_debug.yaml"],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"qrun failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
