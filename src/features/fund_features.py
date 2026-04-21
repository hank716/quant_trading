"""Fundamental features derived from revenue and financial-statement data."""
from __future__ import annotations

import pandas as pd


def _pick_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _to_float(val) -> float | None:
    try:
        f = float(val)
        return f if pd.notna(f) else None
    except (TypeError, ValueError):
        return None


def revenue_momentum(revenue_df: pd.DataFrame) -> dict[str, float | None]:
    """Extract revenue momentum features from a per-stock revenue DataFrame.

    Returns:
        fund_rev_yoy:       latest year-over-year growth rate (fraction, e.g. 0.15 = 15%)
        fund_rev_mom:       latest month-over-month growth rate (fraction)
        fund_rev_consec_pos: consecutive months with positive YoY (count)
    """
    empty = {"fund_rev_yoy": None, "fund_rev_mom": None, "fund_rev_consec_pos": None}
    if revenue_df.empty:
        return empty

    date_col = _pick_col(revenue_df, ["date", "revenue_date", "month_date"])
    rev_col = _pick_col(revenue_df, ["revenue", "month_revenue", "monthly_revenue", "當月營收", "營業收入淨額"])
    if not date_col or not rev_col:
        return empty

    frame = revenue_df.copy()
    frame[rev_col] = pd.to_numeric(frame[rev_col], errors="coerce")
    frame = frame.dropna(subset=[date_col, rev_col]).sort_values(date_col)
    if frame.empty:
        return empty

    # YoY: prefer pre-computed column; otherwise compute from shifted series
    yoy_col = _pick_col(frame, ["revenue_yoy", "yoy", "revenue_year_growth_rate", "month_revenue_change", "營收年增率"])
    if yoy_col:
        latest_yoy_raw = _to_float(frame.iloc[-1][yoy_col])
        # Normalise: if stored as percentage (e.g. 15.0) convert to fraction (0.15)
        if latest_yoy_raw is not None and abs(latest_yoy_raw) > 2:
            latest_yoy = latest_yoy_raw / 100.0
        else:
            latest_yoy = latest_yoy_raw
    else:
        if len(frame) >= 13:
            prev_year_rev = _to_float(frame.iloc[-13][rev_col])
            curr_rev = _to_float(frame.iloc[-1][rev_col])
            latest_yoy = ((curr_rev / prev_year_rev) - 1.0) if (prev_year_rev and curr_rev) else None
        else:
            latest_yoy = None

    # MoM
    mom_col = _pick_col(frame, ["revenue_mom", "mom", "revenue_month_growth_rate", "營收月增率"])
    if mom_col:
        latest_mom_raw = _to_float(frame.iloc[-1][mom_col])
        if latest_mom_raw is not None and abs(latest_mom_raw) > 2:
            latest_mom = latest_mom_raw / 100.0
        else:
            latest_mom = latest_mom_raw
    else:
        if len(frame) >= 2:
            prev_rev = _to_float(frame.iloc[-2][rev_col])
            curr_rev = _to_float(frame.iloc[-1][rev_col])
            latest_mom = ((curr_rev / prev_rev) - 1.0) if (prev_rev and curr_rev) else None
        else:
            latest_mom = None

    # Consecutive positive YoY months
    if yoy_col:
        yoy_series = pd.to_numeric(frame[yoy_col], errors="coerce")
        # Normalise to fraction if stored as percentage
        if yoy_series.abs().median() > 2:
            yoy_series = yoy_series / 100.0
    elif len(frame) >= 13:
        frame["_yoy"] = frame[rev_col] / frame[rev_col].shift(12) - 1.0
        yoy_series = frame["_yoy"]
    else:
        yoy_series = pd.Series(dtype=float)

    consec = 0
    if not yoy_series.empty:
        for v in reversed(yoy_series.dropna().tolist()):
            if v > 0:
                consec += 1
            else:
                break

    return {
        "fund_rev_yoy": round(latest_yoy, 6) if latest_yoy is not None else None,
        "fund_rev_mom": round(latest_mom, 6) if latest_mom is not None else None,
        "fund_rev_consec_pos": consec,
    }


def roe_feature(financial_df: pd.DataFrame) -> dict[str, float | None]:
    """Extract ROE features.

    Returns:
        fund_roe:     latest ROE (fraction, e.g. 0.15 = 15%)
        fund_roe_yoy: change vs. one period ago (fraction difference)
    """
    empty = {"fund_roe": None, "fund_roe_yoy": None}
    if financial_df.empty:
        return empty

    roe_col = _pick_col(financial_df, ["roe_percent", "roe", "roe(%)", "return on equity", "股東權益報酬率"])
    date_col = _pick_col(financial_df, ["date", "period_date", "year", "calendarYear"])
    if not roe_col:
        return empty

    frame = financial_df.copy()
    frame[roe_col] = pd.to_numeric(frame[roe_col], errors="coerce")
    if date_col:
        frame = frame.sort_values(date_col)

    vals = frame[roe_col].dropna()
    if vals.empty:
        return empty

    latest_raw = float(vals.iloc[-1])
    # Normalise percentage → fraction
    latest = latest_raw / 100.0 if abs(latest_raw) > 2 else latest_raw

    roe_yoy = None
    if len(vals) >= 2:
        prev_raw = float(vals.iloc[-2])
        prev = prev_raw / 100.0 if abs(prev_raw) > 2 else prev_raw
        roe_yoy = round(latest - prev, 6)

    return {"fund_roe": round(latest, 6), "fund_roe_yoy": roe_yoy}


def gross_margin_feature(financial_df: pd.DataFrame) -> dict[str, float | None]:
    """Extract gross margin features.

    Returns:
        fund_gm:     latest gross margin (fraction)
        fund_gm_yoy: change vs. one period ago (fraction difference)
    """
    empty = {"fund_gm": None, "fund_gm_yoy": None}
    if financial_df.empty:
        return empty

    gm_col = _pick_col(financial_df, ["gross_margin_percent", "gross margin", "gross_margin", "營業毛利率", "毛利率"])
    date_col = _pick_col(financial_df, ["date", "period_date", "year", "calendarYear"])
    if not gm_col:
        return empty

    frame = financial_df.copy()
    frame[gm_col] = pd.to_numeric(frame[gm_col], errors="coerce")
    if date_col:
        frame = frame.sort_values(date_col)

    vals = frame[gm_col].dropna()
    if vals.empty:
        return empty

    latest_raw = float(vals.iloc[-1])
    latest = latest_raw / 100.0 if abs(latest_raw) > 2 else latest_raw

    gm_yoy = None
    if len(vals) >= 2:
        prev_raw = float(vals.iloc[-2])
        prev = prev_raw / 100.0 if abs(prev_raw) > 2 else prev_raw
        gm_yoy = round(latest - prev, 6)

    return {"fund_gm": round(latest, 6), "fund_gm_yoy": gm_yoy}
