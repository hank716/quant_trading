"""Portfolio YAML editor — atomic read/write for config/portfolio_{profile}.yaml."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml


def _portfolio_path(profile: str) -> Path:
    return Path(f"config/portfolio_{profile}.yaml")


def load_portfolio(profile: str) -> list[dict[str, Any]]:
    """Return holdings as a list of dicts with key 'ticker' added."""
    path = _portfolio_path(profile)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    holdings = data.get("holdings", {})
    result = []
    for ticker, info in holdings.items():
        row = {"ticker": str(ticker), **info}
        result.append(row)
    return result


def save_portfolio(profile: str, holdings: list[dict[str, Any]]) -> None:
    """Atomically write holdings list back to YAML.

    Each item must have 'ticker' key; remaining keys become the holding dict.
    """
    path = _portfolio_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)

    holdings_dict: dict[str, dict] = {}
    for row in holdings:
        row = dict(row)
        ticker = str(row.pop("ticker"))
        holdings_dict[ticker] = row

    data = {"holdings": holdings_dict}
    yaml_str = yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)

    dir_ = path.parent
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(yaml_str)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def add_holding(profile: str, ticker: str, *, name: str = "", asset_type: str = "stock",
                shares: float = 0, avg_cost: float = 0, note: str = "") -> None:
    """Add or replace a holding entry in the portfolio."""
    holdings = load_portfolio(profile)
    existing = [h for h in holdings if h["ticker"] != ticker]
    existing.append({
        "ticker": ticker, "name": name, "asset_type": asset_type,
        "shares": shares, "avg_cost": avg_cost, "note": note,
    })
    save_portfolio(profile, existing)


def remove_holding(profile: str, ticker: str) -> bool:
    """Remove ticker from portfolio. Returns True if it was present."""
    holdings = load_portfolio(profile)
    filtered = [h for h in holdings if h["ticker"] != ticker]
    if len(filtered) == len(holdings):
        return False
    save_portfolio(profile, filtered)
    return True
