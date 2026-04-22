"""TW TopkDropout strategy with hard-rule universe filter."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from qlib.contrib.strategy import TopkDropoutStrategy

logger = logging.getLogger(__name__)

_DEFAULT_EXCLUDE_KEYWORDS = [
    "ETF", "指數", "期信", "貨幣", "債券",
    "權證", "認購", "認售",
    "變更交易", "全額交割",
]


class TwTopkFilteredStrategy(TopkDropoutStrategy):
    """TopkDropout with TW-specific hard rules applied to the score universe.

    Filters applied before topk selection:
    1. Symbol in exclude_symbols list (pre-computed keyword + market-type filter)
    2. $close < min_price
    3. Listed < min_listing_days
    """

    def __init__(
        self,
        *,
        exclude_symbols: list[str] | None = None,
        min_price: float = 10.0,
        min_listing_days: int = 180,
        instruments_file: str = "workspace/qlib_data/instruments/all.txt",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.exclude_symbols: set[str] = set(exclude_symbols or [])
        self.min_price = min_price
        self.min_listing_days = min_listing_days
        self._listing_start: dict[str, str] = {}
        self._load_listing_dates(instruments_file)

    def _load_listing_dates(self, instruments_file: str) -> None:
        """Parse instruments/all.txt to get listing start dates."""
        from pathlib import Path
        path = Path(instruments_file)
        if not path.exists():
            logger.warning("instruments_file not found: %s", path)
            return
        for line in path.read_text().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                self._listing_start[parts[0]] = parts[1]  # symbol → start_date

    def _filter_universe(self, pred_score: pd.Series, trade_date: Any) -> pd.Series:
        """Return pred_score with excluded instruments removed."""
        # 1. Pre-computed exclude list (keywords, market type)
        mask = ~pred_score.index.isin(self.exclude_symbols)
        filtered = pred_score[mask]
        if filtered.empty:
            return filtered

        # 2. Price filter — query $close via Qlib D
        if self.min_price > 0:
            try:
                from qlib.data import D
                prices = D.features(
                    list(filtered.index),
                    ["$close"],
                    start_time=trade_date,
                    end_time=trade_date,
                    freq="day",
                )
                if not prices.empty:
                    prices = prices.groupby(level="instrument")["$close"].last()
                    too_cheap = prices[prices < self.min_price].index
                    filtered = filtered[~filtered.index.isin(too_cheap)]
            except Exception as exc:
                logger.debug("Price filter skipped: %s", exc)

        # 3. Listing-days filter
        if self.min_listing_days > 0 and self._listing_start and trade_date is not None:
            try:
                trade_dt = pd.Timestamp(trade_date)
                young = [
                    sym for sym in filtered.index
                    if sym in self._listing_start
                    and (trade_dt - pd.Timestamp(self._listing_start[sym])).days < self.min_listing_days
                ]
                filtered = filtered[~filtered.index.isin(young)]
            except Exception as exc:
                logger.debug("Listing-days filter skipped: %s", exc)

        removed = len(pred_score) - len(filtered)
        if removed:
            logger.debug("filter_universe: removed %d / %d instruments", removed, len(pred_score))
        return filtered

    def generate_trade_decision(self, execute_result=None):
        """Inject universe filter into the signal before parent logic runs."""
        trade_step = self.trade_calendar.get_trade_step()
        _, trade_end_time = self.trade_calendar.get_step_time(trade_step)

        original_get_signal = self.signal.get_signal

        def _filtered_get_signal(*args, **kwargs):
            score = original_get_signal(*args, **kwargs)
            if score is not None:
                if isinstance(score, pd.DataFrame):
                    score = score.iloc[:, 0]
                score = self._filter_universe(score, trade_end_time)
            return score

        self.signal.get_signal = _filtered_get_signal
        try:
            return super().generate_trade_decision(execute_result)
        finally:
            self.signal.get_signal = original_get_signal
