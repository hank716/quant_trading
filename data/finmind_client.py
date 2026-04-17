from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import md5
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import requests


class FinMindError(RuntimeError):
    pass


@dataclass(slots=True)
class FinMindConfig:
    token: str | None = None
    base_url: str = "https://api.finmindtrade.com/api/v4"
    cache_dir: str = ".cache/finmind"
    timeout: int = 30
    use_mock_data: bool = False
    allow_batch_all_stocks: bool = False


class FinMindClient:
    def __init__(self, config: FinMindConfig):
        self.config = config
        self.cache_dir = Path(config.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()

    @staticmethod
    def _daterange(start: date, end: date) -> Iterable[date]:
        cursor = start
        while cursor <= end:
            yield cursor
            cursor += timedelta(days=1)

    @staticmethod
    def _month_starts(start: date, end: date) -> list[date]:
        cursor = date(start.year, start.month, 1)
        end_marker = date(end.year, end.month, 1)
        values: list[date] = []
        while cursor <= end_marker:
            values.append(cursor)
            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)
        return values

    @staticmethod
    def _quarter_ends(start: date, end: date) -> list[date]:
        quarter_end_month_days = [(3, 31), (6, 30), (9, 30), (12, 31)]
        values: list[date] = []
        year = start.year
        while year <= end.year:
            for month, day in quarter_end_month_days:
                point = date(year, month, day)
                if start <= point <= end:
                    values.append(point)
            year += 1
        return values

    def _cache_path(self, dataset: str, params: dict[str, str]) -> Path:
        payload = "|".join([dataset] + [f"{key}={value}" for key, value in sorted(params.items())])
        digest = md5(payload.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{dataset}_{digest}.json"

    def _read_cached_frame(self, dataset: str, **params: str) -> pd.DataFrame | None:
        cache_path = self._cache_path(dataset, {k: str(v) for k, v in params.items() if v is not None})
        if cache_path.exists():
            return pd.read_json(cache_path)
        return None


    def _cached_dataset_paths(self, dataset: str) -> list[Path]:
        return sorted(self.cache_dir.glob(f"{dataset}_*.json"))

    def _load_cached_dataset(self, dataset: str) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for cache_path in self._cached_dataset_paths(dataset):
            try:
                frame = pd.read_json(cache_path)
            except ValueError:
                continue
            if not frame.empty:
                frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _request_data(self, dataset: str, **params: str) -> pd.DataFrame:
        cached = self._read_cached_frame(dataset, **params)
        if cached is not None:
            return cached

        headers = {}
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"

        query = {"dataset": dataset}
        query.update({k: v for k, v in params.items() if v is not None})

        response = self.session.get(
            f"{self.config.base_url}/data",
            params=query,
            headers=headers,
            timeout=self.config.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        status = payload.get("status", 200)
        if status != 200:
            raise FinMindError(f"FinMind request failed for {dataset}: {payload}")

        frame = pd.DataFrame(payload.get("data", []))
        cache_path = self._cache_path(dataset, {k: str(v) for k, v in params.items() if v is not None})
        frame.to_json(cache_path, orient="records", force_ascii=False)
        return frame

    def _request_batch_point_in_time_dataset(
        self,
        dataset: str,
        stock_ids: list[str],
        point_dates: list[date],
    ) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        wanted = {str(stock_id) for stock_id in stock_ids}
        for point_date in point_dates:
            frame = self._request_data(dataset, start_date=point_date.isoformat())
            if frame.empty or "stock_id" not in frame.columns:
                continue
            if wanted:
                frame = frame[frame["stock_id"].astype(str).isin(wanted)].copy()
            if not frame.empty:
                frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _fetch_dataset_for_stocks(
        self,
        dataset: str,
        stock_ids: list[str],
        start_date: date,
        end_date: date,
        batch_daily: bool = False,
        batch_point_dates: list[date] | None = None,
    ) -> pd.DataFrame:
        if not stock_ids:
            return pd.DataFrame()

        frames: list[pd.DataFrame] = []
        if self.config.allow_batch_all_stocks:
            if batch_daily:
                for day in self._daterange(start_date, end_date):
                    frame = self._request_data(dataset, start_date=day.isoformat())
                    if frame.empty or "stock_id" not in frame.columns:
                        continue
                    frames.append(frame[frame["stock_id"].astype(str).isin(stock_ids)])
            elif batch_point_dates:
                return self._request_batch_point_in_time_dataset(dataset, stock_ids, batch_point_dates)
            else:
                raise FinMindError(
                    f"Batch mode for {dataset} needs either batch_daily=True or explicit batch_point_dates."
                )
        else:
            if len(stock_ids) > 100:
                raise FinMindError(
                    "Per-stock live mode is not practical for large universes. "
                    "Use --stock-limit, enable --allow-premium-batch, or rely on cache/offline data."
                )
            for stock_id in stock_ids:
                frame = self._request_data(
                    dataset,
                    data_id=str(stock_id),
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                )
                if not frame.empty:
                    frames.append(frame)

        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def get_stock_info(self) -> pd.DataFrame:
        if self.config.use_mock_data:
            return self._mock_stock_info()
        return self._request_data("TaiwanStockInfo")

    def get_trading_dates(self, start_date: date, end_date: date) -> pd.DataFrame:
        if self.config.use_mock_data:
            frame = pd.DataFrame({"date": pd.bdate_range(start=start_date, end=end_date).date.astype(str)})
            return frame
        frame = self._request_data("TaiwanStockTradingDate")
        if frame.empty or "date" not in frame.columns:
            return pd.DataFrame(columns=["date"])
        frame = frame.copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.dropna(subset=["date"])
        frame = frame[(frame["date"].dt.date >= start_date) & (frame["date"].dt.date <= end_date)]
        return frame.sort_values("date")

    def get_latest_trading_date(self, as_of_date: date, lookback_days: int = 14) -> date:
        trading_dates = self.get_trading_dates(as_of_date - timedelta(days=lookback_days), as_of_date)
        if trading_dates.empty:
            return as_of_date
        latest = pd.to_datetime(trading_dates["date"]).max()
        return pd.Timestamp(latest).date()

    def get_price_snapshot(self, trade_date: date) -> pd.DataFrame:
        if self.config.use_mock_data:
            frame = self._mock_price_history([row["stock_id"] for row in self._mock_stock_info().to_dict("records")], trade_date, trade_date)
            return frame
        if not self.config.allow_batch_all_stocks:
            cached = self._read_cached_frame("TaiwanStockPrice", start_date=trade_date.isoformat())
            if cached is not None:
                return cached
            raise FinMindError(
                "Liquidity ranking by full-market snapshot requires --allow-premium-batch, "
                "or an existing cached TaiwanStockPrice snapshot for that trading date."
            )
        return self._request_data("TaiwanStockPrice", start_date=trade_date.isoformat())

    def get_price_history(self, stock_ids: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        if self.config.use_mock_data:
            return self._mock_price_history(stock_ids, start_date, end_date)
        return self._fetch_dataset_for_stocks(
            dataset="TaiwanStockPrice",
            stock_ids=stock_ids,
            start_date=start_date,
            end_date=end_date,
            batch_daily=True,
        )

    def get_institutional_buy_sell(self, stock_ids: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        if self.config.use_mock_data:
            return self._mock_institutional_flow(stock_ids, start_date, end_date)
        return self._fetch_dataset_for_stocks(
            dataset="TaiwanStockInstitutionalInvestorsBuySell",
            stock_ids=stock_ids,
            start_date=start_date,
            end_date=end_date,
            batch_daily=True,
        )

    def get_month_revenue(self, stock_ids: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        if self.config.use_mock_data:
            return self._mock_month_revenue(stock_ids, start_date, end_date)
        return self._fetch_dataset_for_stocks(
            dataset="TaiwanStockMonthRevenue",
            stock_ids=stock_ids,
            start_date=start_date,
            end_date=end_date,
            batch_daily=False,
            batch_point_dates=self._month_starts(start_date, end_date),
        )

    def get_financial_statements(self, stock_ids: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        if self.config.use_mock_data:
            return self._mock_financial_statements(stock_ids, start_date, end_date)
        return self._fetch_dataset_for_stocks(
            dataset="TaiwanStockFinancialStatements",
            stock_ids=stock_ids,
            start_date=start_date,
            end_date=end_date,
            batch_daily=False,
            batch_point_dates=self._quarter_ends(start_date, end_date),
        )


    def get_cached_financial_statements(self, stock_ids: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        if self.config.use_mock_data:
            return self._mock_financial_statements(stock_ids, start_date, end_date)

        frame = self._load_cached_dataset("TaiwanStockFinancialStatements")
        if frame.empty:
            return frame

        result = frame.copy()
        if "stock_id" in result.columns:
            result["stock_id"] = result["stock_id"].astype(str)
            if stock_ids:
                wanted = {str(stock_id) for stock_id in stock_ids}
                result = result[result["stock_id"].isin(wanted)].copy()

        if result.empty or "date" not in result.columns:
            return result.reset_index(drop=True)

        result["date"] = pd.to_datetime(result["date"], errors="coerce")
        result = result.dropna(subset=["date"]).copy()
        result = result[(result["date"].dt.date >= start_date) & (result["date"].dt.date <= end_date)]
        if result.empty:
            return result

        result["date"] = result["date"].dt.strftime("%Y-%m-%d")
        dedupe_cols = [col for col in ["stock_id", "date", "type", "value"] if col in result.columns]
        if dedupe_cols:
            result = result.drop_duplicates(subset=dedupe_cols, keep="last")
        return result.reset_index(drop=True)

    @staticmethod
    def _mock_stock_info() -> pd.DataFrame:
        records = [
            {"stock_id": "2330", "stock_name": "TSMC", "industry_category": "Semiconductor", "type": "twse", "date": "1994-09-05"},
            {"stock_id": "2454", "stock_name": "MediaTek", "industry_category": "Semiconductor", "type": "twse", "date": "2001-07-23"},
            {"stock_id": "3008", "stock_name": "Largan", "industry_category": "Optics", "type": "twse", "date": "2002-03-11"},
            {"stock_id": "3661", "stock_name": "Alchip", "industry_category": "IC Design", "type": "tpex", "date": "2014-12-08"},
            {"stock_id": "6147", "stock_name": "ChipMOS", "industry_category": "Semiconductor", "type": "tpex", "date": "2001-05-15"},
            {"stock_id": "1101", "stock_name": "Taiwan Cement", "industry_category": "Cement", "type": "twse", "date": "1962-02-09"},
            {"stock_id": "7777", "stock_name": "NewIPO", "industry_category": "Biotech", "type": "emerging", "date": "2026-03-10"},
            {"stock_id": "00940", "stock_name": "Index ETF", "industry_category": "ETF", "type": "etf", "date": "2024-03-01"},
        ]
        return pd.DataFrame.from_records(records)

    @classmethod
    def _mock_price_history(cls, stock_ids: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        rng = np.random.default_rng(seed=7)
        trading_days = pd.bdate_range(start=start_date, end=end_date)
        base_map = {
            "2330": (920.0, 1.8),
            "2454": (1180.0, 0.2),
            "3008": (1900.0, -1.5),
            "3661": (480.0, 2.2),
            "6147": (48.0, 0.05),
            "1101": (35.0, 0.03),
            "7777": (85.0, 0.8),
            "00940": (10.0, 0.0),
        }
        rows: list[dict[str, object]] = []
        for stock_id in stock_ids:
            base_price, slope = base_map.get(stock_id, (100.0, 0.1))
            for idx, ts in enumerate(trading_days):
                noise = float(rng.normal(0.0, 2.0))
                cycle = 3.0 * np.sin(idx / 6.0)
                close = max(5.0, base_price + slope * idx + cycle + noise)
                open_price = close - float(rng.normal(0.0, 1.0))
                high = max(open_price, close) + abs(float(rng.normal(0.0, 1.5)))
                low = min(open_price, close) - abs(float(rng.normal(0.0, 1.5)))
                volume = int(abs(base_price) * 1000 + rng.integers(10000, 50000))
                rows.append(
                    {
                        "date": ts.date().isoformat(),
                        "stock_id": stock_id,
                        "Trading_Volume": volume,
                        "Trading_money": int(volume * close),
                        "open": round(open_price, 2),
                        "max": round(high, 2),
                        "min": round(low, 2),
                        "close": round(close, 2),
                        "spread": round(close - open_price, 2),
                        "Trading_turnover": float(rng.integers(1000, 9000)),
                    }
                )
        return pd.DataFrame.from_records(rows)

    @classmethod
    def _mock_institutional_flow(cls, stock_ids: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        trading_days = pd.bdate_range(start=start_date, end=end_date)
        rows: list[dict[str, object]] = []
        strength_map = {
            "2330": {"trust": 1200, "foreign": 900, "dealer": 250},
            "2454": {"trust": 300, "foreign": 150, "dealer": 50},
            "3008": {"trust": -600, "foreign": -450, "dealer": -120},
            "3661": {"trust": 900, "foreign": 700, "dealer": 120},
            "6147": {"trust": 150, "foreign": -80, "dealer": 20},
            "1101": {"trust": 20, "foreign": 35, "dealer": -15},
            "7777": {"trust": 450, "foreign": 200, "dealer": 80},
            "00940": {"trust": 0, "foreign": 0, "dealer": 0},
        }
        for stock_id in stock_ids:
            profile = strength_map.get(stock_id, {"trust": 0, "foreign": 0, "dealer": 0})
            for idx, ts in enumerate(trading_days):
                wave = int(120 * np.cos(idx / 5.0))
                trust_net = profile["trust"] + wave
                foreign_net = profile["foreign"] + wave // 2
                dealer_net = profile["dealer"] + wave // 4
                rows.extend(
                    [
                        {
                            "date": ts.date().isoformat(),
                            "stock_id": stock_id,
                            "buy": max(0, 5000 + trust_net),
                            "sell": max(0, 5000),
                            "name": "Investment_Trust",
                        },
                        {
                            "date": ts.date().isoformat(),
                            "stock_id": stock_id,
                            "buy": max(0, 8000 + foreign_net),
                            "sell": max(0, 8000),
                            "name": "Foreign_Investor",
                        },
                        {
                            "date": ts.date().isoformat(),
                            "stock_id": stock_id,
                            "buy": max(0, 2000 + dealer_net),
                            "sell": max(0, 2000),
                            "name": "Dealer_Hedging",
                        },
                    ]
                )
        return pd.DataFrame.from_records(rows)

    @classmethod
    def _mock_month_revenue(cls, stock_ids: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        periods = pd.period_range(start=start_date, end=end_date, freq="M")
        rows: list[dict[str, object]] = []
        base_map = {
            "2330": (220_000.0, 0.08),
            "2454": (45_000.0, 0.04),
            "3008": (15_000.0, -0.03),
            "3661": (12_000.0, 0.12),
            "6147": (5_500.0, 0.01),
            "1101": (10_000.0, 0.02),
            "7777": (1_200.0, 0.20),
            "00940": (0.0, 0.0),
        }
        for stock_id in stock_ids:
            base_revenue, yoy_growth = base_map.get(stock_id, (8_000.0, 0.0))
            for idx, period in enumerate(periods):
                monthly_growth = 0.01 * np.sin(idx / 3.0)
                revenue = base_revenue * (1 + monthly_growth) * (1 + idx * 0.002)
                yoy_pct = yoy_growth * 100 + float(np.cos(idx / 4.0) * 2.5)
                mom_pct = monthly_growth * 100
                rows.append(
                    {
                        "date": period.start_time.date().isoformat(),
                        "stock_id": stock_id,
                        "revenue": round(revenue, 2),
                        "revenue_year": period.year,
                        "revenue_month": period.month,
                        "revenue_yoy": round(yoy_pct, 2),
                        "revenue_mom": round(mom_pct, 2),
                    }
                )
        return pd.DataFrame.from_records(rows)

    @classmethod
    def _mock_financial_statements(cls, stock_ids: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        quarter_dates = pd.date_range(start=start_date, end=end_date, freq="QE")
        rows: list[dict[str, object]] = []
        metric_map = {
            "2330": {"roe": 24.5, "gross_margin": 53.2, "operating_margin": 42.8, "eps": 13.2},
            "2454": {"roe": 18.1, "gross_margin": 46.0, "operating_margin": 23.5, "eps": 8.7},
            "3008": {"roe": 7.5, "gross_margin": 24.0, "operating_margin": 8.2, "eps": 2.1},
            "3661": {"roe": 19.2, "gross_margin": 49.4, "operating_margin": 21.6, "eps": 7.8},
            "6147": {"roe": 5.8, "gross_margin": 17.3, "operating_margin": 6.5, "eps": 0.9},
            "1101": {"roe": 9.3, "gross_margin": 21.8, "operating_margin": 14.5, "eps": 1.8},
            "7777": {"roe": 3.2, "gross_margin": 31.0, "operating_margin": -5.0, "eps": -0.3},
            "00940": {"roe": 0.0, "gross_margin": 0.0, "operating_margin": 0.0, "eps": 0.0},
        }
        for stock_id in stock_ids:
            metrics = metric_map.get(stock_id, {"roe": 5.0, "gross_margin": 20.0, "operating_margin": 10.0, "eps": 1.0})
            for ts in quarter_dates:
                rows.extend(
                    [
                        {"date": ts.date().isoformat(), "stock_id": stock_id, "type": "ROE", "value": metrics["roe"]},
                        {"date": ts.date().isoformat(), "stock_id": stock_id, "type": "營業毛利率", "value": metrics["gross_margin"]},
                        {"date": ts.date().isoformat(), "stock_id": stock_id, "type": "營益率", "value": metrics["operating_margin"]},
                        {"date": ts.date().isoformat(), "stock_id": stock_id, "type": "EPS", "value": metrics["eps"]},
                    ]
                )
        return pd.DataFrame.from_records(rows)
