from __future__ import annotations

from datetime import date, datetime

from data.finmind_client import FinMindClient
from core.models import UniverseStock


class UniverseBuilder:
    def __init__(self, client: FinMindClient, as_of_date: date):
        self.client = client
        self.as_of_date = as_of_date

    @staticmethod
    def _normalize(value: str | None) -> str:
        return (value or "").strip().lower().replace("_", " ")

    def _infer_asset_category(self, row: dict[str, object]) -> str:
        raw_type = self._normalize(str(row.get("type", "")))
        industry = self._normalize(str(row.get("industry_category", "")))
        name = self._normalize(str(row.get("stock_name", "")))
        combined = f"{raw_type} {industry} {name}"
        if any(keyword in combined for keyword in ["etf", "index", "fund"]):
            return "ETF"
        return "Stock"

    def build(
        self,
        stock_limit: int | None = None,
        preferred_stock_ids: list[str] | None = None,
    ) -> list[UniverseStock]:
        frame = self.client.get_stock_info()
        if frame.empty:
            return []

        frame = frame.copy()
        frame["stock_id"] = frame["stock_id"].astype(str)
        frame = frame.sort_values(by=["stock_id", "date"]).drop_duplicates(subset=["stock_id"], keep="last")

        results: list[UniverseStock] = []
        by_stock_id: dict[str, UniverseStock] = {}
        for row in frame.to_dict(orient="records"):
            listed_date = None
            listing_days = None
            raw_date = row.get("date")
            if raw_date:
                try:
                    listed_date = datetime.strptime(str(raw_date), "%Y-%m-%d").date()
                    listing_days = (self.as_of_date - listed_date).days
                except ValueError:
                    listed_date = None
                    listing_days = None

            stock = UniverseStock(
                stock_id=str(row.get("stock_id", "")),
                stock_name=str(row.get("stock_name", "")),
                market_type=str(row.get("type", "unknown")),
                asset_category=self._infer_asset_category(row),
                industry_category=row.get("industry_category"),
                listed_date=listed_date,
                listing_days=listing_days,
            )
            results.append(stock)
            by_stock_id[stock.stock_id] = stock

        if preferred_stock_ids:
            preferred: list[UniverseStock] = []
            seen: set[str] = set()
            for stock_id in preferred_stock_ids:
                stock = by_stock_id.get(str(stock_id))
                if stock and stock.stock_id not in seen:
                    preferred.append(stock)
                    seen.add(stock.stock_id)
            if stock_limit is not None:
                return preferred[:stock_limit]
            if preferred:
                return preferred

        if stock_limit is not None:
            return results[:stock_limit]
        return results
