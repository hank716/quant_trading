"""Assembles the full feature matrix from per-stock data maps."""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.features.tech_features import ma_return, volume_features, institutional_flow_features
from src.features.fund_features import revenue_momentum, roe_feature, gross_margin_feature


def build_feature_matrix(
    universe: list[str],
    price_map: dict[str, pd.DataFrame],
    flow_map: dict[str, pd.DataFrame],
    revenue_map: dict[str, pd.DataFrame],
    financial_map: dict[str, pd.DataFrame],
    trade_date: date,
) -> pd.DataFrame:
    """Build a feature matrix for all stocks in the universe.

    Index: MultiIndex (trade_date, instrument)
    Columns: tech_ma{N}_ret, tech_vol{N}_ratio, tech_fi_net{N}_ratio,
             fund_rev_yoy, fund_rev_mom, fund_rev_consec_pos,
             fund_roe, fund_roe_yoy, fund_gm, fund_gm_yoy

    NaN handling: cross-sectional median fill per column.
    Stocks with no data at all are included with NaN (median-filled).
    """
    rows = []
    for sid in universe:
        price_df = price_map.get(sid, pd.DataFrame())
        flow_df = flow_map.get(sid, pd.DataFrame())
        rev_df = revenue_map.get(sid, pd.DataFrame())
        fin_df = financial_map.get(sid, pd.DataFrame())

        feats: dict = {"trade_date": trade_date, "instrument": sid}
        feats.update(ma_return(price_df))
        feats.update(volume_features(price_df))
        feats.update(institutional_flow_features(flow_df))
        feats.update(revenue_momentum(rev_df))
        feats.update(roe_feature(fin_df))
        feats.update(gross_margin_feature(fin_df))
        rows.append(feats)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index(["trade_date", "instrument"])

    # Cross-sectional median fill: preserves cross-sectional rank structure
    for col in df.columns:
        if df[col].isna().any():
            median = df[col].median()
            if pd.notna(median):
                df[col] = df[col].fillna(median)

    return df
