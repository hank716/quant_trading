from __future__ import annotations

import os
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class HardRules(BaseModel):
    include_markets: list[str] = Field(default_factory=lambda: ["twse", "tpex", "emerging", "etf"])
    exclude_type_keywords: list[str] = Field(default_factory=list)
    exclude_name_keywords: list[str] = Field(default_factory=list)
    min_listing_days: int = 30
    min_price: float | None = 5.0
    max_price: float | None = 3000.0


class PriceRules(BaseModel):
    ma_window: int = 20
    require_close_above_ma: bool = False
    lookback_days: int = 20
    min_return_over_lookback: float | None = -0.1
    max_distance_from_ma: float | None = 0.2


class InstitutionalFlowRule(BaseModel):
    enabled: bool = True
    lookback_days: int = 20
    min_positive_days: int = 4
    min_total_net_buy: float = 0.0
    require_any_major_player: bool = False
    investor_aliases: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "foreign_investor": [
                "foreign investor",
                "foreign",
                "foreign dealer",
                "foreign_",
                "外資",
            ],
            "investment_trust": [
                "investment trust",
                "trust",
                "fund",
                "投信",
            ],
            "dealer": [
                "dealer",
                "proprietary",
                "proprietary trader",
                "self dealer",
                "自營商",
            ],
        }
    )


class MonthlyRevenueRules(BaseModel):
    enabled: bool = True
    min_latest_yoy_percent: float | None = 0.0
    min_latest_mom_percent: float | None = None
    min_consecutive_positive_yoy_months: int | None = 1


class FinancialStatementRules(BaseModel):
    enabled: bool = True
    min_roe_percent: float | None = 5.0
    min_gross_margin_percent: float | None = 15.0
    min_operating_margin_percent: float | None = None


class DecisionRules(BaseModel):
    max_consider: int = 5
    min_signals_for_watch: int = 1
    require_all_signals_for_consider: bool = False
    selection_mode: Literal["rule_based", "llm_assisted"] = "llm_assisted"
    pre_llm_candidate_limit: int = 15
    min_signal_count_for_preselection: int = 1
    max_watch: int = 8


class StrategyConfig(BaseModel):
    strategy_name: str
    strategy_intent: str
    hard_rules: HardRules = Field(default_factory=HardRules)
    price_rules: PriceRules = Field(default_factory=PriceRules)
    institutional_flow: InstitutionalFlowRule = Field(default_factory=InstitutionalFlowRule)
    monthly_revenue: MonthlyRevenueRules = Field(default_factory=MonthlyRevenueRules)
    financial_statement: FinancialStatementRules = Field(default_factory=FinancialStatementRules)
    decision: DecisionRules = Field(default_factory=DecisionRules)


class UniverseStock(BaseModel):
    stock_id: str
    stock_name: str
    market_type: str
    asset_category: str | None = None
    industry_category: str | None = None
    listed_date: date | None = None
    listing_days: int | None = None


class FilterResult(BaseModel):
    passed: bool
    reject_reasons: list[str] = Field(default_factory=list)


class SignalResult(BaseModel):
    all_required_passed: bool
    passed_count: int = 0
    why: list[str] = Field(default_factory=list)
    risk: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class Candidate(BaseModel):
    asset: str
    name: str
    market: str
    asset_category: str | None = None
    industry: str | None = None
    why: list[str] = Field(default_factory=list)
    risk: list[str] = Field(default_factory=list)
    score: float = 0.0
    metrics: dict[str, Any] = Field(default_factory=dict)


class OutputConfig(BaseModel):
    directory: str = Field(default_factory=lambda: os.getenv("OUTPUT_DIR", "outputs"))
    use_profile_subdirectory: bool = True
    json_prefix: str = "daily_result"
    markdown_prefix: str = "daily_report"
    html_prefix: str = "daily_report"


class DiscordConfig(BaseModel):
    enabled: bool = False
    webhook_url: str | None = None
    webhook_url_env: str | None = None
    username: str | None = None
    avatar_url: str | None = None
    mention_text: str | None = None
    include_json_file: bool = True
    include_markdown_file: bool = True
    include_html_file: bool = False 
    include_report_body: bool = True
    max_report_chars: int = 1600
    


class ProfileConfig(BaseModel):
    profile_name: str = "default"
    display_name: str = "預設使用者"
    strategy: str = "config/strategy_1m.yaml"
    portfolio: str = "config/portfolio.yaml"
    selector_provider: str | None = None
    llm_provider: str | None = None
    output: OutputConfig = Field(default_factory=OutputConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)


class DailyResult(BaseModel):
    date: str
    generated_at: str | None = None
    profile_name: str | None = None
    profile_display_name: str | None = None
    strategy: str
    action: Literal["consider", "hold"]
    selection_mode: str | None = None
    eligible_candidates: list[Candidate] = Field(default_factory=list)
    watch_only_candidates: list[Candidate] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    explanation: str | None = None
    llm_payload: dict[str, Any] | None = None
