from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from main import build_data_client, resolve_path
from core.strategy_loader import StrategyLoader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pre-sync official/FinMind data into local cache")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--profile-config", default=None)
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--data-provider", default="official_hybrid", choices=["finmind", "official_hybrid"])
    parser.add_argument("--cache-dir", default=os.path.join(os.getenv("CACHE_DIR", ".cache"), "official_hybrid"))
    parser.add_argument("--lookback-days", type=int, default=35)
    parser.add_argument("--use-mock-data", action="store_true")
    parser.add_argument("--skip-financials", action="store_true", help="official_hybrid 下可跳過快取財報掃描；不會觸發 live 財報 API。")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    load_dotenv(base_dir / ".env.local", override=False)
    load_dotenv(base_dir / ".env", override=False)  # backward-compat fallback
    as_of_date = date.fromisoformat(args.as_of_date)

    client = build_data_client(base_dir, args)
    stock_info = client.get_stock_info()
    stock_ids = stock_info["stock_id"].astype(str).tolist() if not stock_info.empty else []

    latest_trade_date = client.get_latest_trading_date(as_of_date)
    price_start = latest_trade_date - timedelta(days=args.lookback_days)
    price_frame = client.get_price_history(stock_ids, price_start, latest_trade_date)
    flow_frame = client.get_institutional_buy_sell(stock_ids, price_start, latest_trade_date)
    revenue_frame = client.get_month_revenue(stock_ids, as_of_date - timedelta(days=420), as_of_date)
    financial_frame = None
    if not args.skip_financials:
        financial_frame = client.get_financial_statements(stock_ids, as_of_date - timedelta(days=900), as_of_date)

    summary = {
        "data_provider": args.data_provider,
        "cache_dir": str(resolve_path(base_dir, args.cache_dir)),
        "as_of_date": as_of_date.isoformat(),
        "latest_trade_date": latest_trade_date.isoformat(),
        "stock_count": len(stock_ids),
        "price_rows": 0 if price_frame is None else len(price_frame),
        "flow_rows": 0 if flow_frame is None else len(flow_frame),
        "revenue_rows": 0 if revenue_frame is None else len(revenue_frame),
        "financial_rows": 0 if financial_frame is None else len(financial_frame),
        "financial_source": "cache_only" if args.data_provider == "official_hybrid" else "live_or_cache",
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
