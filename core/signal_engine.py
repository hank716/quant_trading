from __future__ import annotations

import math
from typing import Any

import pandas as pd

from core.models import SignalResult, StrategyConfig


class SignalEngine:
    INVESTOR_LABELS = {
        "foreign_investor": "外資",
        "investment_trust": "投信",
        "dealer": "自營商",
    }

    METRIC_ALIASES = {
        "roe_percent": ["roe", "roe(%)", "return on equity", "股東權益報酬率", "權益報酬率"],
        "gross_margin_percent": ["gross margin", "gross_margin", "營業毛利率", "毛利率"],
        "operating_margin_percent": ["operating margin", "operating_margin", "營業利益率", "營益率"],
        "eps": ["eps", "每股盈餘", "基本每股盈餘"],
    }

    def __init__(self, strategy: StrategyConfig):
        self.strategy = strategy

    @staticmethod
    def _normalize(value: str | None) -> str:
        return (value or "").strip().lower().replace("_", " ")

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(numeric) or math.isinf(numeric):
            return None
        return numeric

    @staticmethod
    def _as_percent(value: float | None) -> float | None:
        if value is None:
            return None
        if abs(value) <= 1.5:
            return value * 100.0
        return value

    @staticmethod
    def _round_or_none(value: float | None, digits: int = 4) -> float | None:
        if value is None:
            return None
        return round(value, digits)

    def _evaluate_price_signal(self, price_df: pd.DataFrame) -> tuple[bool, list[str], list[str], dict[str, Any]]:
        rules = self.strategy.price_rules
        why: list[str] = []
        risk: list[str] = []
        metrics: dict[str, Any] = {}

        if price_df.empty or "close" not in price_df.columns or "date" not in price_df.columns:
            risk.append("價格歷史資料不足")
            return False, why, risk, metrics

        frame = price_df.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame.sort_values("date")
        closes = pd.to_numeric(frame["close"], errors="coerce").dropna()

        if len(closes) < max(rules.ma_window, rules.lookback_days):
            risk.append("歷史價格長度不足，無法計算設定視窗")
            return False, why, risk, metrics

        latest_close = float(closes.iloc[-1])
        ma_value = float(closes.tail(rules.ma_window).mean())
        lookback_close = float(closes.iloc[-rules.lookback_days])
        lookback_return = (latest_close / lookback_close) - 1.0 if lookback_close else math.nan
        distance_from_ma = ((latest_close / ma_value) - 1.0) if ma_value else math.nan

        metrics.update(
            {
                "latest_close": round(latest_close, 4),
                "ma_value": round(ma_value, 4),
                "lookback_return": round(float(lookback_return), 6),
                "distance_from_ma": round(float(distance_from_ma), 6),
            }
        )

        passed = True
        if rules.require_close_above_ma:
            if latest_close > ma_value:
                why.append(f"價格站穩 MA{rules.ma_window}")
            else:
                risk.append(f"價格跌破 MA{rules.ma_window}")
                passed = False

        if rules.min_return_over_lookback is not None:
            if lookback_return >= rules.min_return_over_lookback:
                why.append(f"近 {rules.lookback_days} 日報酬仍在可接受範圍")
            else:
                risk.append(f"近 {rules.lookback_days} 日報酬弱於最低門檻")
                passed = False

        if rules.max_distance_from_ma is not None:
            if distance_from_ma <= rules.max_distance_from_ma:
                why.append("價格未明顯偏離均線，沒有過度追價")
            else:
                risk.append("價格偏離均線過大，可能有追價風險")
                passed = False

        return passed, why, risk, metrics

    def _classify_investor(self, raw_name: str | None) -> str | None:
        normalized_name = self._normalize(raw_name)
        for participant, aliases in self.strategy.institutional_flow.investor_aliases.items():
            if any(self._normalize(alias) in normalized_name for alias in aliases):
                return participant
        return None

    def _evaluate_flow_signal(self, flow_df: pd.DataFrame) -> tuple[bool, list[str], list[str], dict[str, Any]]:
        rules = self.strategy.institutional_flow
        if not rules.enabled:
            return True, [], [], {}

        why: list[str] = []
        risk: list[str] = []
        metrics: dict[str, Any] = {}

        if flow_df.empty or not {"date", "buy", "sell", "name"}.issubset(flow_df.columns):
            risk.append("法人買賣資料不足")
            return False, why, risk, metrics

        frame = flow_df.copy()
        frame["investor_key"] = frame["name"].astype(str).map(self._classify_investor)
        frame = frame[frame["investor_key"].notna()].copy()
        if frame.empty:
            risk.append("無法辨識外資、投信、自營商資料")
            return False, why, risk, metrics

        frame["date"] = pd.to_datetime(frame["date"])
        frame["buy"] = pd.to_numeric(frame["buy"], errors="coerce").fillna(0.0)
        frame["sell"] = pd.to_numeric(frame["sell"], errors="coerce").fillna(0.0)
        frame["net_buy"] = frame["buy"] - frame["sell"]

        participant_breakdown: dict[str, Any] = {}
        positive_major_players: list[str] = []
        for participant, label in self.INVESTOR_LABELS.items():
            sub = frame[frame["investor_key"] == participant]
            if sub.empty:
                continue
            daily_net = sub.groupby("date", as_index=False)["net_buy"].sum().sort_values("date").tail(rules.lookback_days)
            if daily_net.empty:
                continue
            positive_days = int((daily_net["net_buy"] > 0).sum())
            total_net_buy = float(daily_net["net_buy"].sum())
            latest_net_buy = float(daily_net.iloc[-1]["net_buy"])
            participant_breakdown[participant] = {
                "label": label,
                "positive_days": positive_days,
                "total_net_buy": round(total_net_buy, 4),
                "latest_net_buy": round(latest_net_buy, 4),
                "window_days": int(len(daily_net)),
            }
            if total_net_buy > 0 and positive_days >= max(1, rules.min_positive_days // 2):
                positive_major_players.append(label)
                why.append(f"{label}近 {len(daily_net)} 日有 {positive_days} 日買超，累計買超 {total_net_buy:.0f}")
            elif total_net_buy < 0:
                risk.append(f"{label}近 {len(daily_net)} 日偏賣超，累計淨流出 {abs(total_net_buy):.0f}")

        overall_daily = frame.groupby("date", as_index=False)["net_buy"].sum().sort_values("date").tail(rules.lookback_days)
        if overall_daily.empty:
            risk.append("法人資料彙整後為空")
            return False, why, risk, metrics

        positive_days = int((overall_daily["net_buy"] > 0).sum())
        total_net_buy = float(overall_daily["net_buy"].sum())
        metrics.update(
            {
                "positive_flow_days": positive_days,
                "total_net_buy": round(total_net_buy, 4),
                "institutional_breakdown": participant_breakdown,
            }
        )

        passed = True
        if positive_days >= rules.min_positive_days:
            why.append(f"三大法人合計在近 {len(overall_daily)} 日中，有 {positive_days} 日買超")
        else:
            risk.append(f"三大法人合計買超天數不足：{positive_days} < {rules.min_positive_days}")
            passed = False

        if total_net_buy >= rules.min_total_net_buy:
            why.append("三大法人合計買超量達到門檻")
        else:
            risk.append(f"三大法人合計買超量不足：{total_net_buy:.2f} < {rules.min_total_net_buy:.2f}")
            passed = False

        if rules.require_any_major_player:
            if positive_major_players:
                why.append(f"主要買盤來源：{'、'.join(dict.fromkeys(positive_major_players))}")
            else:
                risk.append("看不到明確由外資、投信或自營商主導的買盤")
                passed = False

        return passed, why, risk, metrics

    @staticmethod
    def _pick_first_existing_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
        normalized_map = {col.lower(): col for col in frame.columns}
        for candidate in candidates:
            if candidate.lower() in normalized_map:
                return normalized_map[candidate.lower()]
        return None

    def _evaluate_monthly_revenue_signal(self, revenue_df: pd.DataFrame) -> tuple[bool, list[str], list[str], dict[str, Any]]:
        rules = self.strategy.monthly_revenue
        if not rules.enabled:
            return True, [], [], {}

        why: list[str] = []
        risk: list[str] = []
        metrics: dict[str, Any] = {}

        if revenue_df.empty:
            risk.append("月營收資料不足")
            return False, why, risk, metrics

        frame = revenue_df.copy()
        date_col = self._pick_first_existing_column(frame, ["date", "revenue_date", "month_date"])
        revenue_col = self._pick_first_existing_column(
            frame,
            ["revenue", "month_revenue", "monthly_revenue", "當月營收", "營業收入淨額"],
        )
        if not date_col or not revenue_col:
            risk.append("月營收資料缺少必要欄位")
            return False, why, risk, metrics

        frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
        frame[revenue_col] = pd.to_numeric(frame[revenue_col], errors="coerce")
        frame = frame.dropna(subset=[date_col, revenue_col]).copy()
        if frame.empty:
            risk.append("月營收資料無有效數值")
            return False, why, risk, metrics

        year_col = self._pick_first_existing_column(frame, ["revenue_year", "year"])
        month_col = self._pick_first_existing_column(frame, ["revenue_month", "month"])
        if year_col and month_col:
            frame["year"] = pd.to_numeric(frame[year_col], errors="coerce").fillna(frame[date_col].dt.year)
            frame["month"] = pd.to_numeric(month_col and frame[month_col], errors="coerce").fillna(frame[date_col].dt.month)
        else:
            frame["year"] = frame[date_col].dt.year
            frame["month"] = frame[date_col].dt.month

        frame["period"] = pd.to_datetime(
            {
                "year": frame["year"].astype(int),
                "month": frame["month"].astype(int),
                "day": 1,
            },
            errors="coerce",
        )
        frame = frame.dropna(subset=["period"]).sort_values("period")
        frame = frame.drop_duplicates(subset=["period"], keep="last")
        if len(frame) < 3:
            risk.append("月營收歷史長度不足")
            return False, why, risk, metrics

        yoy_col = self._pick_first_existing_column(
            frame,
            ["revenue_yoy", "yoy", "revenue_year_growth_rate", "month_revenue_change", "營收年增率"],
        )
        mom_col = self._pick_first_existing_column(
            frame,
            ["revenue_mom", "mom", "revenue_month_growth_rate", "營收月增率"],
        )
        if yoy_col:
            frame["yoy_pct"] = pd.to_numeric(frame[yoy_col], errors="coerce")
            frame["yoy_pct"] = frame["yoy_pct"].map(self._as_percent)
        else:
            frame["prev_year_revenue"] = frame[revenue_col].shift(12)
            frame["yoy_pct"] = ((frame[revenue_col] / frame["prev_year_revenue"]) - 1.0) * 100.0

        if mom_col:
            frame["mom_pct"] = pd.to_numeric(frame[mom_col], errors="coerce")
            frame["mom_pct"] = frame["mom_pct"].map(self._as_percent)
        else:
            frame["prev_month_revenue"] = frame[revenue_col].shift(1)
            frame["mom_pct"] = ((frame[revenue_col] / frame["prev_month_revenue"]) - 1.0) * 100.0

        latest = frame.iloc[-1]
        latest_yoy = self._to_float(latest.get("yoy_pct"))
        latest_mom = self._to_float(latest.get("mom_pct"))
        latest_revenue = self._to_float(latest.get(revenue_col))
        latest_period = latest.get("period")

        streak = 0
        for value in reversed(frame["yoy_pct"].tolist()):
            numeric = self._to_float(value)
            if numeric is None or numeric <= 0:
                break
            streak += 1

        metrics.update(
            {
                "latest_revenue": self._round_or_none(latest_revenue, 2),
                "latest_revenue_yoy_percent": self._round_or_none(latest_yoy, 2),
                "latest_revenue_mom_percent": self._round_or_none(latest_mom, 2),
                "positive_yoy_streak_months": streak,
                "revenue_latest_month": None if pd.isna(latest_period) else pd.Timestamp(latest_period).strftime("%Y-%m"),
            }
        )

        passed = True
        if latest_yoy is None:
            risk.append("無法判斷最新月營收年增率")
            passed = False
        elif rules.min_latest_yoy_percent is not None:
            if latest_yoy >= rules.min_latest_yoy_percent:
                why.append(f"最新月營收年增 {latest_yoy:.2f}%")
            else:
                risk.append(
                    f"最新月營收年增不足：{latest_yoy:.2f}% < {rules.min_latest_yoy_percent:.2f}%"
                )
                passed = False

        if rules.min_latest_mom_percent is not None:
            if latest_mom is not None and latest_mom >= rules.min_latest_mom_percent:
                why.append(f"最新月營收月增 {latest_mom:.2f}%")
            else:
                risk.append("最新月營收月增未達設定門檻")
                passed = False

        if rules.min_consecutive_positive_yoy_months is not None:
            if streak >= rules.min_consecutive_positive_yoy_months:
                why.append(f"月營收已連續 {streak} 個月年增")
            else:
                risk.append(
                    f"月營收連續年增月數不足：{streak} < {rules.min_consecutive_positive_yoy_months}"
                )
                passed = False

        return passed, why, risk, metrics

    def _extract_financial_metric_map(self, financial_df: pd.DataFrame) -> dict[str, Any]:
        frame = financial_df.copy()
        if frame.empty:
            return {}

        date_col = self._pick_first_existing_column(frame, ["date", "release_date", "publish_date", "report_date"])
        if date_col is None:
            return {}

        frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
        frame = frame.dropna(subset=[date_col]).copy()
        if frame.empty:
            return {}

        latest_date = frame[date_col].max()
        latest_frame = frame[frame[date_col] == latest_date].copy()
        result: dict[str, Any] = {"latest_financial_date": pd.Timestamp(latest_date).strftime("%Y-%m-%d")}

        for metric_name, aliases in self.METRIC_ALIASES.items():
            wide_col = self._pick_first_existing_column(latest_frame, aliases)
            value: float | None = None
            if wide_col:
                value = self._to_float(latest_frame.iloc[-1].get(wide_col))
            else:
                name_col = self._pick_first_existing_column(latest_frame, ["type", "name", "origin_name", "title", "item"])
                value_col = self._pick_first_existing_column(latest_frame, ["value", "amount", "number"])
                if name_col and value_col:
                    normalized_aliases = [self._normalize(alias) for alias in aliases]
                    matched = latest_frame[
                        latest_frame[name_col].astype(str).map(
                            lambda raw: any(alias in self._normalize(raw) for alias in normalized_aliases)
                        )
                    ]
                    if not matched.empty:
                        value = self._to_float(matched.iloc[0].get(value_col))

            if metric_name.endswith("_percent"):
                value = self._as_percent(value)
            result[metric_name] = self._round_or_none(value, 2)

        return result

    def _evaluate_financial_statement_signal(self, financial_df: pd.DataFrame) -> tuple[bool, list[str], list[str], dict[str, Any]]:
        rules = self.strategy.financial_statement
        if not rules.enabled:
            return True, [], [], {}

        why: list[str] = []
        risk: list[str] = []
        metrics = self._extract_financial_metric_map(financial_df)
        if not metrics:
            risk.append("財報資料不足")
            return False, why, risk, {}

        passed = True
        roe = self._to_float(metrics.get("roe_percent"))
        gross_margin = self._to_float(metrics.get("gross_margin_percent"))
        operating_margin = self._to_float(metrics.get("operating_margin_percent"))

        if rules.min_roe_percent is not None:
            if roe is not None and roe >= rules.min_roe_percent:
                why.append(f"最新財報 ROE 為 {roe:.2f}%")
            else:
                risk.append("最新財報 ROE 未達門檻")
                passed = False

        if rules.min_gross_margin_percent is not None:
            if gross_margin is not None and gross_margin >= rules.min_gross_margin_percent:
                why.append(f"最新財報毛利率為 {gross_margin:.2f}%")
            else:
                risk.append("最新財報毛利率未達門檻")
                passed = False

        if rules.min_operating_margin_percent is not None:
            if operating_margin is not None and operating_margin >= rules.min_operating_margin_percent:
                why.append(f"最新財報營業利益率為 {operating_margin:.2f}%")
            else:
                risk.append("最新財報營業利益率未達門檻")
                passed = False

        metrics["financial_snapshot"] = {
            "roe_percent": metrics.get("roe_percent"),
            "gross_margin_percent": metrics.get("gross_margin_percent"),
            "operating_margin_percent": metrics.get("operating_margin_percent"),
            "eps": metrics.get("eps"),
        }
        return passed, why, risk, metrics

    def evaluate(
        self,
        price_df: pd.DataFrame,
        flow_df: pd.DataFrame,
        revenue_df: pd.DataFrame,
        financial_df: pd.DataFrame,
    ) -> SignalResult:
        price_passed, price_why, price_risk, price_metrics = self._evaluate_price_signal(price_df)
        flow_passed, flow_why, flow_risk, flow_metrics = self._evaluate_flow_signal(flow_df)
        revenue_passed, revenue_why, revenue_risk, revenue_metrics = self._evaluate_monthly_revenue_signal(revenue_df)
        financial_passed, financial_why, financial_risk, financial_metrics = self._evaluate_financial_statement_signal(financial_df)

        signal_flags = {
            "price": price_passed,
            "institutional_flow": flow_passed,
            "monthly_revenue": revenue_passed,
            "financial_statement": financial_passed,
        }
        passed_count = sum(int(flag) for flag in signal_flags.values())
        why = price_why + flow_why + revenue_why + financial_why
        risk = price_risk + flow_risk + revenue_risk + financial_risk
        metrics: dict[str, Any] = {
            **price_metrics,
            **flow_metrics,
            **revenue_metrics,
            **financial_metrics,
            "signal_breakdown": signal_flags,
        }

        enabled_checks = [
            price_passed,
            flow_passed if self.strategy.institutional_flow.enabled else True,
            revenue_passed if self.strategy.monthly_revenue.enabled else True,
            financial_passed if self.strategy.financial_statement.enabled else True,
        ]
        all_required = all(enabled_checks)

        score = float(passed_count)
        score += max(self._to_float(metrics.get("positive_flow_days")) or 0.0, 0.0) / 100.0
        score += max(self._to_float(metrics.get("lookback_return")) or 0.0, -1.0)
        score += max((self._to_float(metrics.get("latest_revenue_yoy_percent")) or 0.0) / 100.0, -0.5)
        score += max((self._to_float(metrics.get("roe_percent")) or 0.0) / 100.0, 0.0)
        score += max((self._to_float(metrics.get("gross_margin_percent")) or 0.0) / 200.0, 0.0)
        metrics["ranking_score"] = round(score, 6)

        return SignalResult(
            all_required_passed=all_required,
            passed_count=passed_count,
            why=why,
            risk=risk,
            metrics=metrics,
        )
