"""Retrain gate — determines when to trigger a model retrain."""
from datetime import date, timedelta
from typing import Optional

# Defaults: tune via env or pass explicitly
DEFAULT_MIN_DAYS_BETWEEN_RETRAINS = 30
DEFAULT_REVENUE_COVERAGE_THRESHOLD = 0.70
DEFAULT_FINANCIAL_COVERAGE_THRESHOLD = 0.60
DEFAULT_MAX_MISSING_CRITICAL = 0


def should_trigger_retrain(
    snapshot: dict,
    last_retrain_date: Optional[date],
    today: Optional[date] = None,
    min_days: int = DEFAULT_MIN_DAYS_BETWEEN_RETRAINS,
    revenue_threshold: float = DEFAULT_REVENUE_COVERAGE_THRESHOLD,
    financial_threshold: float = DEFAULT_FINANCIAL_COVERAGE_THRESHOLD,
    max_missing_critical: int = DEFAULT_MAX_MISSING_CRITICAL,
) -> tuple[bool, str]:
    """Return (should_retrain: bool, reason: str).

    Trigger conditions (any one is sufficient):
    1. Revenue coverage drops below threshold
    2. Financial coverage drops below threshold
    3. Critical stocks are missing
    4. min_days have elapsed since last retrain (or never retrained)
    """
    today = today or date.today()
    rev_cov = snapshot.get("revenue_coverage", 1.0)
    fin_cov = snapshot.get("financial_coverage", 1.0)
    missing_critical = snapshot.get("missing_critical", [])

    if rev_cov < revenue_threshold:
        return True, f"revenue_coverage {rev_cov:.1%} < threshold {revenue_threshold:.1%}"

    if fin_cov < financial_threshold:
        return True, f"financial_coverage {fin_cov:.1%} < threshold {financial_threshold:.1%}"

    if len(missing_critical) > max_missing_critical:
        return True, f"{len(missing_critical)} critical stock(s) missing: {missing_critical[:5]}"

    if last_retrain_date is None:
        return True, "no previous retrain found"

    days_since = (today - last_retrain_date).days
    if days_since >= min_days:
        return True, f"{days_since} days since last retrain (threshold: {min_days})"

    return False, f"coverage ok, {days_since}/{min_days} days since last retrain"


def build_retrain_decision(
    snapshot: dict,
    last_retrain_date: Optional[date],
    today: Optional[date] = None,
    **gate_kwargs,
) -> dict:
    """Return a retrain decision dict suitable for JSON serialisation.

    Includes the trigger verdict, reason, and supporting coverage metrics.
    """
    today = today or date.today()
    trigger, reason = should_trigger_retrain(
        snapshot, last_retrain_date, today=today, **gate_kwargs
    )
    return {
        "trade_date": snapshot.get("trade_date", today.isoformat()),
        "evaluated_at": today.isoformat(),
        "should_retrain": trigger,
        "reason": reason,
        "last_retrain_date": last_retrain_date.isoformat() if last_retrain_date else None,
        "days_since_retrain": (today - last_retrain_date).days if last_retrain_date else None,
        "revenue_coverage": snapshot.get("revenue_coverage"),
        "financial_coverage": snapshot.get("financial_coverage"),
        "missing_critical_count": len(snapshot.get("missing_critical", [])),
    }
