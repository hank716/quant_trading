"""Technical features derived from price and institutional-flow data."""
from __future__ import annotations

import pandas as pd


def _pick_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def ma_return(
    price_df: pd.DataFrame,
    windows: list[int] | None = None,
) -> dict[str, float | None]:
    """Return price / MA(window) - 1 for each window.

    Feature names: ``tech_ma{N}_ret``.
    Returns NaN for a window if price history is too short.
    """
    windows = windows or [5, 10, 20, 60]
    result: dict[str, float | None] = {}

    if price_df.empty or "close" not in price_df.columns:
        return {f"tech_ma{w}_ret": None for w in windows}

    closes = (
        pd.to_numeric(price_df["close"], errors="coerce")
        .dropna()
        .reset_index(drop=True)
    )
    latest = closes.iloc[-1] if len(closes) > 0 else None

    for w in windows:
        key = f"tech_ma{w}_ret"
        if latest is None or len(closes) < w:
            result[key] = None
        else:
            ma = float(closes.tail(w).mean())
            result[key] = round((latest / ma) - 1.0, 6) if ma else None

    return result


def volume_features(
    price_df: pd.DataFrame,
    windows: list[int] | None = None,
) -> dict[str, float | None]:
    """Return recent rolling average volume / baseline average volume.

    Feature names: ``tech_vol{N}_ratio``.
    Baseline is the full series mean; ratio > 1 means above-average activity.
    """
    windows = windows or [5, 20]
    result: dict[str, float | None] = {}

    vol_col = _pick_col(price_df, ["Trading_Volume", "volume", "成交股數", "成交仟股", "trade volume"])
    if price_df.empty or vol_col is None:
        return {f"tech_vol{w}_ratio": None for w in windows}

    vols = pd.to_numeric(price_df[vol_col], errors="coerce").dropna().reset_index(drop=True)
    baseline = float(vols.mean()) if len(vols) > 0 else None

    for w in windows:
        key = f"tech_vol{w}_ratio"
        if baseline is None or baseline == 0 or len(vols) < w:
            result[key] = None
        else:
            rolling_mean = float(vols.tail(w).mean())
            result[key] = round(rolling_mean / baseline, 6)

    return result


def institutional_flow_features(
    flow_df: pd.DataFrame,
    windows: list[int] | None = None,
) -> dict[str, float | None]:
    """Return rolling net-buy sum normalised by total traded value.

    Feature names: ``tech_fi_net{N}_ratio``.
    Positive → net buying pressure; negative → net selling pressure.
    Normalisation: divide by sum(|buy| + |sell|) over the same window.
    """
    windows = windows or [5, 20]
    result: dict[str, float | None] = {}

    required = {"date", "buy", "sell"}
    if flow_df.empty or not required.issubset(flow_df.columns):
        return {f"tech_fi_net{w}_ratio": None for w in windows}

    frame = flow_df.copy()
    frame["net_buy"] = pd.to_numeric(frame["buy"], errors="coerce") - pd.to_numeric(frame["sell"], errors="coerce")
    frame["gross"] = pd.to_numeric(frame["buy"], errors="coerce").abs() + pd.to_numeric(frame["sell"], errors="coerce").abs()

    # Aggregate across all institutions per date
    daily = (
        frame.groupby("date", as_index=False)
        .agg(net_buy=("net_buy", "sum"), gross=("gross", "sum"))
        .sort_values("date")
    )

    for w in windows:
        key = f"tech_fi_net{w}_ratio"
        tail = daily.tail(w)
        if len(tail) < 1:
            result[key] = None
            continue
        net_sum = float(tail["net_buy"].sum())
        gross_sum = float(tail["gross"].sum())
        result[key] = round(net_sum / gross_sum, 6) if gross_sum > 0 else None

    return result
