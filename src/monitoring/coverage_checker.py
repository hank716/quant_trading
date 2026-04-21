"""Daily data coverage checker — tracks revenue and financial statement completeness."""
from datetime import date
from typing import Optional

import pandas as pd


def compute_revenue_coverage(
    universe: list[str],
    revenue_map: dict[str, pd.DataFrame],
    trade_date: date,
) -> dict:
    """Return coverage stats for monthly revenue data.

    Args:
        universe: list of stock_id strings to check
        revenue_map: {stock_id: DataFrame} from data fetch
        trade_date: reference date (for snapshot metadata)
    """
    total = len(universe)
    if total == 0:
        return {"coverage_pct": 0.0, "covered": 0, "total": 0, "missing": [], "trade_date": trade_date.isoformat()}

    missing = [sid for sid in universe if revenue_map.get(sid, pd.DataFrame()).empty]
    covered = total - len(missing)
    return {
        "coverage_pct": round(covered / total, 4),
        "covered": covered,
        "total": total,
        "missing": missing,
        "trade_date": trade_date.isoformat(),
    }


def compute_financial_coverage(
    universe: list[str],
    financial_map: dict[str, pd.DataFrame],
    trade_date: date,
) -> dict:
    """Return coverage stats for financial statement data.

    Args:
        universe: list of stock_id strings to check
        financial_map: {stock_id: DataFrame} from data fetch
        trade_date: reference date (for snapshot metadata)
    """
    total = len(universe)
    if total == 0:
        return {"coverage_pct": 0.0, "covered": 0, "total": 0, "missing": [], "trade_date": trade_date.isoformat()}

    missing = [sid for sid in universe if financial_map.get(sid, pd.DataFrame()).empty]
    covered = total - len(missing)
    return {
        "coverage_pct": round(covered / total, 4),
        "covered": covered,
        "total": total,
        "missing": missing,
        "trade_date": trade_date.isoformat(),
    }


def find_missing_critical(coverage: dict, critical_ids: list[str]) -> list[str]:
    """Return which critical stocks are missing from coverage.

    Args:
        coverage: result from compute_*_coverage (contains "missing" list)
        critical_ids: stock IDs that must be present (e.g. current portfolio)
    """
    missing_set = set(coverage.get("missing", []))
    return [sid for sid in critical_ids if sid in missing_set]


def build_coverage_snapshot(
    trade_date: date,
    rev_cov: dict,
    fin_cov: dict,
    missing_critical: Optional[list[str]] = None,
) -> dict:
    """Combine revenue and financial coverage into a single snapshot dict.

    This dict is suitable for writing to workspace/runs/{run_id}/coverage_snapshot.json
    and inserting into Supabase coverage_snapshots table.
    """
    return {
        "trade_date": trade_date.isoformat(),
        "revenue_coverage": rev_cov.get("coverage_pct", 0.0),
        "revenue_covered": rev_cov.get("covered", 0),
        "revenue_total": rev_cov.get("total", 0),
        "financial_coverage": fin_cov.get("coverage_pct", 0.0),
        "financial_covered": fin_cov.get("covered", 0),
        "financial_total": fin_cov.get("total", 0),
        "missing_critical": missing_critical or [],
    }
