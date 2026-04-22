"""CLI: python -m app.orchestration.sync_qlib_data --lookback-days 5"""
from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


def _build_client():
    from data.official_hybrid_client import OfficialHybridClient, OfficialHybridConfig

    return OfficialHybridClient(
        OfficialHybridConfig(
            cache_dir=os.getenv("CACHE_DIR", "workspace/hotdata"),
            use_mock_data=os.getenv("USE_MOCK_DATA", "false").lower() == "true",
            finmind_token=os.getenv("FINMIND_TOKEN"),
        )
    )


def main(lookback_days: int = 5) -> None:
    """Run all Qlib data collectors and update the binary store."""
    from qlib_ext.data_collector.financial_collector import FinancialCollector
    from qlib_ext.data_collector.merge_universe import merge_and_write_instruments
    from qlib_ext.data_collector.tpex_collector import TPExCollector
    from qlib_ext.data_collector.twse_collector import TWSECollector

    staging_root = Path(os.getenv("CACHE_DIR", "workspace")) / "qlib_data_csv"
    provider_uri = Path(os.getenv("OUTPUT_DIR", "workspace")) / "qlib_data"
    start_date = date.today() - timedelta(days=lookback_days)
    end_date = date.today()

    t0 = time.monotonic()
    client = _build_client()

    twse = TWSECollector(client, staging_root / "twse", provider_uri)
    tpex = TPExCollector(client, staging_root / "tpex", provider_uri)

    twse_symbols = twse.collect(start_date, end_date)
    tpex_symbols = tpex.collect(start_date, end_date)

    all_raw_symbols = [s.removesuffix(".TW") for s in twse_symbols + tpex_symbols]
    financial = FinancialCollector(client, staging_root / "financial")
    financial.collect(all_raw_symbols, start_date, end_date)

    merge_and_write_instruments(twse_symbols, tpex_symbols, provider_uri)

    twse.dump_to_bin()
    tpex.dump_to_bin()

    elapsed = time.monotonic() - t0
    total = len(twse_symbols) + len(tpex_symbols)
    print(f"sync_qlib_data: {total} symbols updated in {elapsed:.1f}s")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--lookback-days", type=int, default=5)
    args = parser.parse_args()
    main(lookback_days=args.lookback_days)
