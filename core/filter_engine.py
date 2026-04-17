from __future__ import annotations

from core.models import FilterResult, HardRules, UniverseStock


class FilterEngine:
    def __init__(self, rules: HardRules):
        self.rules = rules

    @staticmethod
    def _normalize(value: str | None) -> str:
        return (value or "").strip().lower().replace("_", " ")

    def evaluate(self, stock: UniverseStock, latest_price: float | None) -> FilterResult:
        reasons: list[str] = []

        market = self._normalize(stock.market_type)
        include_markets = [self._normalize(item) for item in self.rules.include_markets]
        if include_markets and not any(item in market for item in include_markets):
            reasons.append(f"market not allowed: {stock.market_type}")

        combined_text = f"{stock.stock_name} {stock.market_type} {stock.asset_category or ''} {stock.industry_category or ''}"
        normalized_text = self._normalize(combined_text)
        for keyword in self.rules.exclude_type_keywords + self.rules.exclude_name_keywords:
            if self._normalize(keyword) in normalized_text:
                reasons.append(f"excluded by keyword: {keyword}")
                break

        if stock.listing_days is None:
            reasons.append("missing listing_days")
        elif stock.listing_days < self.rules.min_listing_days:
            reasons.append(
                f"listing_days below threshold: {stock.listing_days} < {self.rules.min_listing_days}"
            )

        if latest_price is None:
            reasons.append("missing latest price")
        else:
            if self.rules.min_price is not None and latest_price < self.rules.min_price:
                reasons.append(
                    f"price below minimum: {latest_price:.2f} < {self.rules.min_price:.2f}"
                )
            if self.rules.max_price is not None and latest_price > self.rules.max_price:
                reasons.append(
                    f"price above maximum: {latest_price:.2f} > {self.rules.max_price:.2f}"
                )

        return FilterResult(passed=not reasons, reject_reasons=reasons)
