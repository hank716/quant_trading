"""Unit tests for TWSECollector and TPExCollector — mock price data, no real API."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

qlib = pytest.importorskip("qlib", reason="pyqlib not installed")

from qlib_ext.data_collector.twse_collector import TWSECollector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_price_df() -> pd.DataFrame:
    rows = []
    for code in ["2330", "2317", "2454"]:
        for i, d in enumerate(pd.date_range("2024-01-02", periods=5, freq="B")):
            rows.append(
                {
                    "stock_id": code,
                    "date": d.strftime("%Y-%m-%d"),
                    "open": 100.0 + i,
                    "max": 105.0 + i,
                    "min": 99.0 + i,
                    "close": 102.0 + i,
                    "Trading_Volume": 1_000_000,
                }
            )
    return pd.DataFrame(rows)


def _make_collector(tmp_path: Path) -> tuple[TWSECollector, MagicMock]:
    client = MagicMock()
    client.get_stock_info.return_value = pd.DataFrame(
        {"stock_id": ["2330", "2317", "2454"], "market_type": ["TWSE", "TWSE", "TWSE"]}
    )
    client.get_price_history.return_value = _make_price_df()

    staging_dir = tmp_path / "staging"
    provider_uri = tmp_path / "qlib_data"
    collector = TWSECollector(client, staging_dir, provider_uri)
    return collector, client


# ---------------------------------------------------------------------------
# collect() — CSV output
# ---------------------------------------------------------------------------

def test_collect_creates_csv_per_symbol(tmp_path):
    collector, _ = _make_collector(tmp_path)
    written = collector.collect(date(2024, 1, 2), date(2024, 1, 8))

    assert len(written) == 3
    for sym in ["2330.TW", "2317.TW", "2454.TW"]:
        csv_path = tmp_path / "staging" / f"{sym}.csv"
        assert csv_path.exists(), f"Missing CSV: {csv_path}"


def test_collect_csv_has_required_columns(tmp_path):
    collector, _ = _make_collector(tmp_path)
    collector.collect(date(2024, 1, 2), date(2024, 1, 8))

    csv_path = tmp_path / "staging" / "2330.TW.csv"
    df = pd.read_csv(csv_path)
    for col in ["date", "open", "high", "low", "close", "volume", "factor"]:
        assert col in df.columns, f"Missing column: {col}"


def test_collect_csv_is_non_empty(tmp_path):
    collector, _ = _make_collector(tmp_path)
    collector.collect(date(2024, 1, 2), date(2024, 1, 8))

    csv_path = tmp_path / "staging" / "2330.TW.csv"
    df = pd.read_csv(csv_path)
    assert len(df) > 0


def test_collect_factor_column_is_one(tmp_path):
    collector, _ = _make_collector(tmp_path)
    collector.collect(date(2024, 1, 2), date(2024, 1, 8))

    csv_path = tmp_path / "staging" / "2330.TW.csv"
    df = pd.read_csv(csv_path)
    assert (df["factor"] == 1.0).all()


def test_collect_with_explicit_symbols(tmp_path):
    collector, client = _make_collector(tmp_path)
    client.get_price_history.return_value = _make_price_df()[
        lambda d: d["stock_id"].isin(["2330"])
    ]
    written = collector.collect(date(2024, 1, 2), date(2024, 1, 8), symbols=["2330"])

    assert written == ["2330.TW"]
    assert client.get_stock_info.call_count == 0


def test_collect_empty_dataframe_returns_no_files(tmp_path):
    collector, client = _make_collector(tmp_path)
    client.get_price_history.return_value = pd.DataFrame()
    written = collector.collect(date(2024, 1, 2), date(2024, 1, 8))

    assert written == []


# ---------------------------------------------------------------------------
# dump_to_bin() — requires qlib DumpDataAll
# ---------------------------------------------------------------------------

def test_dump_to_bin_creates_bin_files(tmp_path):
    from qlib.data.dump_bin import DumpDataAll  # skip if qlib not installed

    collector, _ = _make_collector(tmp_path)
    collector.collect(date(2024, 1, 2), date(2024, 1, 8))
    collector.dump_to_bin()

    features_dir = tmp_path / "qlib_data" / "features"
    bin_files = list(features_dir.rglob("*.bin"))
    assert len(bin_files) > 0, "dump_to_bin produced no .bin files"


# ---------------------------------------------------------------------------
# merge_and_write_instruments
# ---------------------------------------------------------------------------

def test_merge_and_write_instruments(tmp_path):
    from qlib_ext.data_collector.merge_universe import merge_and_write_instruments

    out = merge_and_write_instruments(
        ["2330.TW", "2317.TW"],
        ["3008.TW"],
        tmp_path / "qlib_data",
    )
    assert out.exists()
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 3
    symbols_in_file = {line.split("\t")[0] for line in lines}
    assert "2330.TW" in symbols_in_file
    assert "3008.TW" in symbols_in_file
