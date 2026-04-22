"""Benchmark collector: TAIEX (^TWII) and OTC (^TWOII) → Qlib bin."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_BENCHMARKS = {
    "^TWII": "taiex",  # TWSE index
    "^TWOII": "otc",   # OTC index
}


class BenchmarkCollector:
    """Collects TAIEX/OTC close prices and writes to Qlib binary format."""

    def __init__(self, staging_dir: Path, provider_uri: Path) -> None:
        self._staging_dir = Path(staging_dir)
        self._provider_uri = Path(provider_uri)

    def collect(self, client: Any, start_date: date, end_date: date) -> list[str]:
        """Fetch benchmark data via client and stage as CSVs.

        Gracefully skips if client doesn't support index data.
        Returns list of staged benchmark symbols.
        """
        self._staging_dir.mkdir(parents=True, exist_ok=True)
        staged = []
        for symbol in _BENCHMARKS:
            try:
                rows = self._fetch_index(client, symbol, start_date, end_date)
                if rows:
                    out = self._staging_dir / f"{symbol}.csv"
                    df = pd.DataFrame(rows, columns=["date", "close"])
                    df = df.sort_values("date").drop_duplicates("date")
                    if out.exists():
                        existing = pd.read_csv(out, parse_dates=["date"])
                        existing["date"] = existing["date"].dt.strftime("%Y-%m-%d")
                        df = pd.concat([existing, df]).drop_duplicates("date").sort_values("date")
                    df.to_csv(out, index=False)
                    staged.append(symbol)
                    logger.info("Staged %d rows for %s", len(df), symbol)
            except Exception as exc:
                logger.warning("Could not fetch %s: %s", symbol, exc)
        return staged

    def _fetch_index(self, client: Any, symbol: str, start: date, end: date) -> list[tuple]:
        """Try to fetch index data; raises if not available."""
        # OfficialHybridClient doesn't expose index directly — placeholder for future
        raise NotImplementedError(f"Index fetch not implemented for {symbol}")

    def dump_to_bin(self) -> None:
        """Write staged CSVs to Qlib binary format."""
        csv_files = list(self._staging_dir.glob("*.csv"))
        if not csv_files:
            logger.info("No benchmark CSVs to dump")
            return

        # Load existing calendar from provider_uri for alignment
        cal_path = self._provider_uri / "calendars" / "day.txt"
        if not cal_path.exists():
            logger.warning("Calendar not found at %s — skipping benchmark dump", cal_path)
            return

        calendar = cal_path.read_text().splitlines()
        date_to_idx = {d: i for i, d in enumerate(calendar)}

        for csv_path in csv_files:
            symbol = csv_path.stem          # e.g. "^TWII"
            symbol_lower = symbol.lower()   # e.g. "^twii"
            df = pd.read_csv(csv_path, parse_dates=["date"])
            df["date"] = df["date"].dt.strftime("%Y-%m-%d")
            df = df[df["date"].isin(date_to_idx)].sort_values("date")

            if df.empty:
                logger.warning("No calendar-aligned rows for %s", symbol)
                continue

            feat_dir = self._provider_uri / "features" / symbol_lower
            feat_dir.mkdir(parents=True, exist_ok=True)

            start_idx = date_to_idx[df["date"].iloc[0]]
            values = df["close"].astype("float32").to_numpy()
            payload = np.concatenate([[np.float32(start_idx)], values])
            payload.astype("<f4").tofile(feat_dir / "close.day.bin")
            logger.info("Wrote benchmark bin: %s → %s", symbol, feat_dir)

        # Update instruments/all.txt to include benchmarks
        inst_path = self._provider_uri / "instruments" / "all.txt"
        if inst_path.exists():
            existing_lines = inst_path.read_text().splitlines()
            existing = {line.split("\t")[0]: line for line in existing_lines if line.strip()}
            for csv_path in csv_files:
                symbol = csv_path.stem
                df = pd.read_csv(csv_path, parse_dates=["date"])
                df["date"] = df["date"].dt.strftime("%Y-%m-%d")
                if not df.empty:
                    existing[symbol] = f"{symbol}\t{df['date'].min()}\t{df['date'].max()}"
            inst_path.write_text("\n".join(sorted(existing.values())) + "\n")
