"""Converts monthly revenue and quarterly financials → daily-frequency Qlib CSV files."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class FinancialCollector:
    """Converts monthly revenue + quarterly financials → daily-frequency bin files."""

    def __init__(self, client, staging_dir: Path) -> None:
        self._client = client
        self._staging_dir = Path(staging_dir)
        self._staging_dir.mkdir(parents=True, exist_ok=True)

    def _symbol_to_qlib(self, code: str) -> str:
        return f"{code}.TW"

    def _ffill_to_daily(
        self,
        df: pd.DataFrame,
        date_col: str,
        value_col: str,
        start_date: date,
        end_date: date,
    ) -> pd.Series:
        """Forward-fill a low-frequency series to a daily index."""
        daily_idx = pd.date_range(str(start_date), str(end_date), freq="D")
        if df.empty:
            return pd.Series(float("nan"), index=daily_idx, name=value_col)

        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col]).sort_values(date_col)
        series = df.set_index(date_col)[value_col]
        series = series[~series.index.duplicated(keep="last")]
        series = series.reindex(daily_idx)
        series = series.ffill()
        return series

    def collect(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> None:
        """Fetch and write forward-filled revenue, ROE, and gross margin CSV files."""
        for code in symbols:
            qlib_symbol = self._symbol_to_qlib(code)
            sym_dir = self._staging_dir / qlib_symbol
            sym_dir.mkdir(parents=True, exist_ok=True)

            self._write_revenue(code, qlib_symbol, sym_dir, start_date, end_date)
            self._write_financials(code, qlib_symbol, sym_dir, start_date, end_date)

        logger.info("FinancialCollector wrote data for %d symbols", len(symbols))

    def _write_revenue(
        self,
        code: str,
        qlib_symbol: str,
        sym_dir: Path,
        start_date: date,
        end_date: date,
    ) -> None:
        try:
            rev_df = self._client.get_month_revenue([code], start_date, end_date)
        except Exception as exc:
            logger.warning("[%s] get_month_revenue failed: %s", qlib_symbol, exc)
            rev_df = pd.DataFrame()

        val_col = "revenue" if "revenue" in (rev_df.columns if not rev_df.empty else []) else (
            rev_df.columns[-1] if not rev_df.empty and len(rev_df.columns) > 1 else "revenue"
        )

        series = self._ffill_to_daily(rev_df, "date", val_col, start_date, end_date)
        df_out = series.reset_index()
        df_out.columns = ["date", "revenue"]
        df_out["date"] = df_out["date"].dt.strftime("%Y-%m-%d")
        df_out.to_csv(sym_dir / "revenue.csv", index=False)

    def _write_financials(
        self,
        code: str,
        qlib_symbol: str,
        sym_dir: Path,
        start_date: date,
        end_date: date,
    ) -> None:
        try:
            fin_df = self._client.get_financial_statements([code], start_date, end_date)
        except Exception as exc:
            logger.warning("[%s] get_financial_statements failed: %s", qlib_symbol, exc)
            fin_df = pd.DataFrame()

        daily_idx = pd.date_range(str(start_date), str(end_date), freq="D")

        for col_name, out_name in [("roe", "roe"), ("gross_margin", "gm")]:
            has_col = not fin_df.empty and col_name in fin_df.columns
            series = self._ffill_to_daily(
                fin_df if has_col else pd.DataFrame(),
                "date",
                col_name,
                start_date,
                end_date,
            )
            df_out = series.reset_index()
            df_out.columns = ["date", out_name]
            df_out["date"] = df_out["date"].dt.strftime("%Y-%m-%d")
            df_out.to_csv(sym_dir / f"{out_name}.csv", index=False)
