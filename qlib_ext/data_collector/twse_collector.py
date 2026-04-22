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
        """Call DumpDataAll on the staging CSVs → write to provider_uri."""
        try:
            from qlib.data.dump_bin import DumpDataAll
        except ImportError:
            logger.error("pyqlib is not installed — skipping dump_to_bin")
            return

        self._provider_uri.mkdir(parents=True, exist_ok=True)
        dumper = DumpDataAll(
            csv_path=str(self._staging_dir),
            qlib_dir=str(self._provider_uri),
            max_workers=4,
            date_field_name="date",
            symbol_field_name=None,
            include_fields=["open", "high", "low", "close", "volume", "factor"],
        )
        dumper.dump(calc_features_and_dump_day=False)
        logger.info("[%s] dump_to_bin completed → %s", self.MARKET_TYPE, self._provider_uri)
