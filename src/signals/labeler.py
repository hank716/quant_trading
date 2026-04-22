"""Label generation for supervised learning — forward-return target."""
from __future__ import annotations

import pandas as pd


def compute_forward_return(
    price_df: pd.DataFrame,
    horizon_days: int = 20,
) -> pd.Series:
    """Compute per-bar forward return over ``horizon_days`` trading days.

    Args:
        price_df: DataFrame with columns ``date`` and ``close``, sorted asc.
        horizon_days: look-ahead window (trading days).

    Returns:
        Series indexed by ``date``; NaN for the last ``horizon_days`` bars
        where no future close is available.
    """
    if price_df.empty or "close" not in price_df.columns or "date" not in price_df.columns:
        return pd.Series(dtype=float, name="forward_return")

    frame = (
        price_df[["date", "close"]]
        .copy()
        .assign(close=lambda d: pd.to_numeric(d["close"], errors="coerce"))
        .dropna(subset=["close"])
        .sort_values("date")
        .reset_index(drop=True)
    )

    frame["forward_return"] = (
        frame["close"].shift(-horizon_days) / frame["close"] - 1.0
    )
    return frame.set_index("date")["forward_return"]


def binary_label(
    forward_return: pd.Series,
    threshold: float = 0.0,
) -> pd.Series:
    """Convert forward-return series to binary label (1 = outperform, 0 = not).

    NaN entries are propagated as NaN (caller should drop before training).
    """
    return (forward_return > threshold).where(forward_return.notna()).astype("Int64")
