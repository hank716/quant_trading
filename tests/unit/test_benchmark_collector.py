"""Unit tests for BenchmarkCollector."""
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np
import pytest


def _make_provider_uri(tmp_path: Path) -> Path:
    # Create minimal calendar
    cal_dir = tmp_path / "calendars"
    cal_dir.mkdir(parents=True)
    dates = pd.date_range("2025-01-02", periods=10, freq="B")
    (cal_dir / "day.txt").write_text("\n".join(d.strftime("%Y-%m-%d") for d in dates) + "\n")
    (tmp_path / "instruments").mkdir()
    (tmp_path / "instruments" / "all.txt").write_text("2330.TW\t2025-01-02\t2025-01-13\n")
    return tmp_path


def test_dump_to_bin_writes_bin(tmp_path):
    from qlib_ext.data_collector.benchmark_collector import BenchmarkCollector

    staging = tmp_path / "staging"
    staging.mkdir()
    provider_uri = _make_provider_uri(tmp_path / "qlib_data")

    dates = pd.date_range("2025-01-02", periods=5, freq="B")
    df = pd.DataFrame({"date": [d.strftime("%Y-%m-%d") for d in dates], "close": [100.0]*5})
    df.to_csv(staging / "^TWII.csv", index=False)

    collector = BenchmarkCollector(staging, provider_uri)
    collector.dump_to_bin()

    bin_path = provider_uri / "features" / "^twii" / "close.day.bin"
    assert bin_path.exists()
    data = np.fromfile(bin_path, dtype="<f4")
    assert len(data) == 6  # start_idx + 5 values


def test_dump_to_bin_no_csv_is_noop(tmp_path):
    from qlib_ext.data_collector.benchmark_collector import BenchmarkCollector
    staging = tmp_path / "staging"
    staging.mkdir()
    provider_uri = tmp_path / "qlib_data"
    provider_uri.mkdir()
    (provider_uri / "calendars").mkdir()
    (provider_uri / "calendars" / "day.txt").write_text("2025-01-02\n")
    collector = BenchmarkCollector(staging, provider_uri)
    collector.dump_to_bin()  # no error, no output
