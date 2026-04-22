"""Merges TWSE and TPEx symbol lists and writes instruments/all.txt."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_EARLIEST_DATE = "2000-01-01"
_LATEST_DATE = "2099-12-31"


def merge_and_write_instruments(
    twse_symbols: list[str],
    tpex_symbols: list[str],
    provider_uri: Path,
    start_date: str = _EARLIEST_DATE,
    end_date: str = _LATEST_DATE,
) -> Path:
    """Write instruments/all.txt in Qlib format: symbol TAB start_date TAB end_date."""
    instruments_dir = Path(provider_uri) / "instruments"
    instruments_dir.mkdir(parents=True, exist_ok=True)
    out_path = instruments_dir / "all.txt"

    all_symbols = sorted(set(twse_symbols) | set(tpex_symbols))
    lines = [f"{sym}\t{start_date}\t{end_date}" for sym in all_symbols]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    logger.info("Wrote %d instruments to %s", len(all_symbols), out_path)
    return out_path
