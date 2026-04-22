"""Reads cached TWSE daily price data and writes Qlib CSV staging files."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_REQUIRED_COLS = {"date", "open", "high", "low", "close", "volume"}


class TWSECollector:
    """Reads cached TWSE daily price data → writes Qlib CSV staging files."""

    MARKET_TYPE = "TWSE"

    def __init__(self, client, staging_dir: Path, provider_uri: Path) -> None:
        self._client = client
        self._staging_dir = Path(staging_dir)
        self._provider_uri = Path(provider_uri)
        self._staging_dir.mkdir(parents=True, exist_ok=True)

    def _symbol_to_qlib(self, code: str) -> str:
        return f"{code}.TW"

    def _get_symbols(self, symbols: list[str] | None) -> list[str]:
        if symbols is not None:
            return symbols
        try:
            universe = self._client.get_stock_info()
            if "market_type" in universe.columns:
                universe = universe[universe["market_type"] == self.MARKET_TYPE]
            col = "stock_id" if "stock_id" in universe.columns else universe.columns[0]
            return universe[col].astype(str).tolist()
        except Exception as exc:
            logger.warning("Could not fetch universe, returning empty list: %s", exc)
            return []

    def collect(
        self,
        start_date: date,
        end_date: date,
        symbols: list[str] | None = None,
    ) -> list[str]:
        """Fetch price history for all symbols and write CSV per symbol.

        Returns the list of Qlib-format symbol names that were written.
        """
        raw_symbols = self._get_symbols(symbols)
        if not raw_symbols:
            logger.warning("[%s] No symbols to collect", self.MARKET_TYPE)
            return []

        df = self._client.get_price_history(raw_symbols, start_date, end_date)
        if df is None or df.empty:
            logger.warning("[%s] get_price_history returned empty DataFrame", self.MARKET_TYPE)
            return []

        df = df.copy()

        id_col = "stock_id" if "stock_id" in df.columns else df.columns[0]
        rename = {
            id_col: "symbol",
            "max": "high",
            "min": "low",
            "Trading_Volume": "volume",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                df[col] = float("nan")

        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df["factor"] = 1.0

        written: list[str] = []
        for code, group in df.groupby("symbol"):
            qlib_symbol = self._symbol_to_qlib(str(code))
            out_path = self._staging_dir / f"{qlib_symbol}.csv"
            out_cols = ["date", "open", "high", "low", "close", "volume", "factor"]
            group = group[out_cols].sort_values("date").drop_duplicates("date")
            group.to_csv(out_path, index=False)
            written.append(qlib_symbol)

        logger.info("[%s] Wrote %d symbol CSVs to %s", self.MARKET_TYPE, len(written), self._staging_dir)
        return written

    def dump_to_bin(self) -> None:
        """Convert staging CSVs to Qlib binary format (little-endian float32).

        Builds calendars/day.txt, instruments/all.txt, and per-field .day.bin
        files under provider_uri/features/{symbol}/.  This avoids DumpDataAll
        which was removed from pyqlib 0.9.8+.
        """
        import numpy as np

        csv_files = sorted(self._staging_dir.glob("*.csv"))
        if not csv_files:
            logger.warning("[%s] No staging CSVs found — nothing to dump", self.MARKET_TYPE)
            return

        self._provider_uri.mkdir(parents=True, exist_ok=True)

        # 1. Collect all trading dates across every symbol
        all_dates: set[str] = set()
        frames: dict[str, pd.DataFrame] = {}
        for csv_path in csv_files:
            symbol = csv_path.stem  # e.g. "2330.TW"
            df = pd.read_csv(csv_path, parse_dates=["date"])
            df["date"] = df["date"].dt.strftime("%Y-%m-%d")
            df = df.sort_values("date").drop_duplicates("date")
            frames[symbol] = df
            all_dates.update(df["date"].tolist())

        calendar: list[str] = sorted(all_dates)
        date_to_idx: dict[str, int] = {d: i for i, d in enumerate(calendar)}

        # 2. Write calendars/day.txt
        cal_dir = self._provider_uri / "calendars"
        cal_dir.mkdir(parents=True, exist_ok=True)
        (cal_dir / "day.txt").write_text("\n".join(calendar) + "\n")

        # 3. Write instruments/all.txt (append-safe merge)
        inst_dir = self._provider_uri / "instruments"
        inst_dir.mkdir(parents=True, exist_ok=True)
        inst_path = inst_dir / "all.txt"
        existing: dict[str, str] = {}
        if inst_path.exists():
            for line in inst_path.read_text().splitlines():
                parts = line.split("\t")
                if parts:
                    existing[parts[0]] = line
        for symbol, df in frames.items():
            start = df["date"].iloc[0]
            end = df["date"].iloc[-1]
            existing[symbol] = f"{symbol}\t{start}\t{end}"
        inst_path.write_text("\n".join(sorted(existing.values())) + "\n")

        # 4. Write feature bin files
        fields = ["open", "high", "low", "close", "volume", "factor"]
        for symbol, df in frames.items():
            feat_dir = self._provider_uri / "features" / symbol.lower()
            feat_dir.mkdir(parents=True, exist_ok=True)
            for field in fields:
                if field not in df.columns:
                    continue
                start_idx = date_to_idx[df["date"].iloc[0]]
                values = df[field].astype("float32").to_numpy()
                # Qlib bin layout: [start_index_f32, val0, val1, ...]
                payload = np.concatenate([[np.float32(start_idx)], values])
                payload.astype("<f4").tofile(feat_dir / f"{field}.day.bin")

        logger.info(
            "[%s] dump_to_bin: %d symbols, %d calendar days → %s",
            self.MARKET_TYPE, len(frames), len(calendar), self._provider_uri,
        )
