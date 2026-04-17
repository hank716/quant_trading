from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from hashlib import md5
from pathlib import Path

from dotenv import load_dotenv

from data.finmind_client import FinMindClient, FinMindConfig, FinMindError
from data.official_hybrid_client import OfficialHybridClient, OfficialHybridConfig


def resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return base_dir / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Slow, quota-friendly quarterly financial sync worker")
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--start-date", default=None, help="預設為 as_of_date 往前 900 天")
    parser.add_argument("--end-date", default=None, help="預設為 as_of_date")
    parser.add_argument("--batch-size", type=int, default=30)
    parser.add_argument("--cursor-file", default=".cache/finmind/financial_sync_cursor.json")
    parser.add_argument("--official-cache-dir", default=".cache/official_hybrid")
    parser.add_argument("--cache-dir", default=".cache/finmind")
    parser.add_argument("--reset-cursor", action="store_true")
    parser.add_argument("--use-mock-data", action="store_true")
    return parser.parse_args()


def load_cursor(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_cursor(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    load_dotenv(base_dir / ".env")

    as_of_date = date.fromisoformat(args.as_of_date)
    start_date = date.fromisoformat(args.start_date) if args.start_date else as_of_date - timedelta(days=900)
    end_date = date.fromisoformat(args.end_date) if args.end_date else as_of_date

    token = os.getenv("FINMIND_TOKEN")
    if not args.use_mock_data and not token:
        raise SystemExit("FINMIND_TOKEN 未設定；slow financial sync 需要 token。")

    official_client = OfficialHybridClient(
        OfficialHybridConfig(
            cache_dir=str(resolve_path(base_dir, args.official_cache_dir)),
            use_mock_data=args.use_mock_data,
            finmind_token=token,
            finmind_cache_dir=str(resolve_path(base_dir, args.cache_dir)),
            use_finmind_financials_cache=True,
        )
    )
    stock_info = official_client.get_stock_info()
    stock_ids = sorted(stock_info["stock_id"].astype(str).tolist()) if not stock_info.empty else []

    universe_hash = md5(",".join(stock_ids).encode("utf-8")).hexdigest() if stock_ids else "empty"
    cursor_path = resolve_path(base_dir, args.cursor_file)
    cursor = {} if args.reset_cursor else load_cursor(cursor_path)
    next_index = int(cursor.get("next_index", 0)) if cursor.get("universe_hash") == universe_hash else 0

    if next_index >= len(stock_ids):
        next_index = 0

    batch_stock_ids = stock_ids[next_index : next_index + max(args.batch_size, 1)]
    if not batch_stock_ids and stock_ids:
        next_index = 0
        batch_stock_ids = stock_ids[: max(args.batch_size, 1)]

    client = FinMindClient(
        FinMindConfig(
            token=token,
            cache_dir=str(resolve_path(base_dir, args.cache_dir)),
            use_mock_data=args.use_mock_data,
            allow_batch_all_stocks=False,
        )
    )

    frame = client.get_financial_statements(batch_stock_ids, start_date, end_date) if batch_stock_ids else client.get_financial_statements([], start_date, end_date)
    next_cursor = next_index + len(batch_stock_ids)
    completed_cycle = False
    if next_cursor >= len(stock_ids):
        next_cursor = 0
        completed_cycle = bool(stock_ids)

    save_cursor(
        cursor_path,
        {
            "universe_hash": universe_hash,
            "next_index": next_cursor,
            "last_batch_stock_ids": batch_stock_ids,
            "last_run_at": as_of_date.isoformat(),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
    )

    summary = {
        "mode": "financial_slow_sync",
        "cache_dir": str(resolve_path(base_dir, args.cache_dir)),
        "cursor_file": str(cursor_path),
        "as_of_date": as_of_date.isoformat(),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "batch_size": args.batch_size,
        "selected_count": len(batch_stock_ids),
        "selected_stock_ids": batch_stock_ids,
        "rows_fetched": len(frame),
        "next_index": next_cursor,
        "completed_cycle": completed_cycle,
        "stock_count": len(stock_ids),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
