"""Integration test: Qlib can initialize and read TW bin data."""
from __future__ import annotations

import pytest
from pathlib import Path

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not Path("workspace/qlib_data/instruments/all.txt").exists(),
    reason="No Qlib bin data available — run sync_qlib_data first",
)
def test_features_read():
    qlib = pytest.importorskip("qlib", reason="pyqlib not installed")
    import qlib.data as D

    from qlib_ext import init_tw_qlib

    init_tw_qlib()
    df = D.features(
        ["2330.TW"],
        ["$close"],
        start_time="2024-01-01",
        end_time="2024-01-31",
    )
    assert not df.empty
