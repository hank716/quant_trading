from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

import pandas as pd

from core.filter_engine import FilterEngine
from core.models import Candidate, DailyResult, StrategyConfig, UniverseStock
from core.signal_engine import SignalEngine


class DecisionEngine:
    def __init__(self, strategy: StrategyConfig, portfolio_snapshot: dict[str, dict[str, Any]], as_of_date: date):
        self.strategy = strategy
        self.portfolio_snapshot = portfolio_snapshot
        self.as_of_date = as_of_date
        self.filter_engine = FilterEngine(strategy.hard_rules)
        self.signal_engine = SignalEngine(strategy)

    @staticmethod
    def _latest_close(price_df: pd.DataFrame) -> float | None:
        if price_df.empty or "close" not in price_df.columns:
            return None
        frame = price_df.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame.sort_values("date")
        if frame.empty:
            return None
        return float(frame.iloc[-1]["close"])

    def _candidate_risks(self, stock: UniverseStock, signal_risk: list[str]) -> list[str]:
        risks = list(signal_risk)
        if stock.stock_id in self.portfolio_snapshot:
            holding = self.portfolio_snapshot[stock.stock_id]
            holding_name = holding.get("name") or stock.stock_id
            risks.append(f"已存在於目前庫存股：{holding_name}")
        return risks

    def _build_candidate(self, stock: UniverseStock, signal_result) -> Candidate:
        return Candidate(
            asset=stock.stock_id,
            name=stock.stock_name,
            market=stock.market_type,
            asset_category=stock.asset_category,
            industry=stock.industry_category,
            why=signal_result.why,
            risk=self._candidate_risks(stock, signal_result.risk),
            score=float(signal_result.metrics.get("ranking_score", signal_result.passed_count)),
            metrics=signal_result.metrics,
        )

    @staticmethod
    def _merge_selector_output(candidate: Candidate, selection_item: dict[str, Any]) -> Candidate:
        enriched = candidate.model_copy(deep=True)
        metrics = dict(enriched.metrics)
        metrics.update(
            {
                "llm_verdict": selection_item.get("verdict"),
                "llm_confidence": selection_item.get("confidence"),
                "llm_summary": selection_item.get("summary"),
                "llm_bull_points": selection_item.get("bull_points", []),
                "llm_bear_points": selection_item.get("bear_points", []),
                "llm_invalidation_conditions": selection_item.get("invalidation_conditions", []),
            }
        )
        enriched.metrics = metrics
        return enriched

    def _apply_rule_based_decision(self, candidate_pool: list[Candidate]) -> tuple[list[Candidate], list[Candidate], list[str], str]:
        eligible: list[Candidate] = []
        watch_only: list[Candidate] = []

        for candidate in candidate_pool:
            signal_breakdown = candidate.metrics.get("signal_breakdown", {})
            passed_count = sum(int(bool(value)) for value in signal_breakdown.values())
            if self.strategy.decision.require_all_signals_for_consider:
                qualifies = all(bool(value) for value in signal_breakdown.values())
            else:
                qualifies = passed_count >= max(1, self.strategy.decision.min_signals_for_watch + 1)

            if qualifies:
                eligible.append(candidate)
            elif passed_count >= self.strategy.decision.min_signals_for_watch:
                watch_only.append(candidate)

        eligible = eligible[: self.strategy.decision.max_consider]
        watch_only = watch_only[: self.strategy.decision.max_watch]
        notes = [
            "本次結果由規則式排名決定，尚未套用 LLM 深度判讀。",
            f"可進一步思考標的: {len(eligible)}",
            f"僅觀察標的: {len(watch_only)}",
        ]
        action = "consider" if eligible else "hold"
        return eligible, watch_only, notes, action

    def _apply_llm_selection(self, candidate_pool: list[Candidate], selector) -> tuple[list[Candidate], list[Candidate], list[str], str]:
        preselected = candidate_pool[: self.strategy.decision.pre_llm_candidate_limit]
        if not preselected:
            return [], [], ["沒有足夠的候選標的可交給 LLM 判讀。"], "hold"

        selection_result = selector.select(preselected, self.strategy, self.portfolio_snapshot)
        item_map = {item.get("asset"): item for item in selection_result.get("selections", [])}

        eligible: list[Candidate] = []
        watch_only: list[Candidate] = []
        for candidate in preselected:
            item = item_map.get(candidate.asset)
            if not item:
                continue
            enriched = self._merge_selector_output(candidate, item)
            verdict = item.get("verdict")
            if verdict == "consider" and len(eligible) < self.strategy.decision.max_consider:
                eligible.append(enriched)
            elif verdict == "watch" and len(watch_only) < self.strategy.decision.max_watch:
                watch_only.append(enriched)

        notes = [
            f"已先用 FinMind 資料做摘要，再交給 LLM 從前 {len(preselected)} 檔候選中判讀。",
            f"LLM 市場觀察：{selection_result.get('market_observation', '')}",
            f"LLM 投組提醒：{selection_result.get('portfolio_note', '')}",
            f"可進一步思考標的: {len(eligible)}",
            f"僅觀察標的: {len(watch_only)}",
        ]
        action = "consider" if eligible else str(selection_result.get("overall_action") or "hold")
        if action not in {"consider", "hold"}:
            action = "consider" if eligible else "hold"
        return eligible, watch_only, notes, action

    def run(
        self,
        universe: list[UniverseStock],
        price_map: dict[str, pd.DataFrame],
        flow_map: dict[str, pd.DataFrame],
        revenue_map: dict[str, pd.DataFrame],
        financial_map: dict[str, pd.DataFrame],
        selector=None,
    ) -> DailyResult:
        candidate_pool: list[Candidate] = []
        reject_count = 0
        insufficient_signal_count = 0
        reject_reason_counter: Counter[str] = Counter()

        for stock in universe:
            price_df = price_map.get(stock.stock_id, pd.DataFrame())
            flow_df = flow_map.get(stock.stock_id, pd.DataFrame())
            revenue_df = revenue_map.get(stock.stock_id, pd.DataFrame())
            financial_df = financial_map.get(stock.stock_id, pd.DataFrame())
            latest_price = self._latest_close(price_df)

            filter_result = self.filter_engine.evaluate(stock, latest_price)
            if not filter_result.passed:
                reject_count += 1
                if filter_result.reject_reasons:
                    reject_reason_counter.update(filter_result.reject_reasons)
                else:
                    reject_reason_counter.update(["unknown reject reason"])
                continue

            signal_result = self.signal_engine.evaluate(price_df, flow_df, revenue_df, financial_df)
            if signal_result.passed_count < self.strategy.decision.min_signal_count_for_preselection:
                insufficient_signal_count += 1
                continue

            candidate_pool.append(self._build_candidate(stock, signal_result))

        candidate_pool.sort(key=lambda item: item.score, reverse=True)

        notes = [
            f"掃描股票數: {len(universe)}",
            f"被硬規則淘汰: {reject_count}",
            f"訊號不足未進入候選池: {insufficient_signal_count}",
            f"進入候選池數量: {len(candidate_pool)}",
            "本版策略不預設排除 ETF，由 LLM 與規則共同挑選今天值得研究的標的。",
        ]
        if reject_reason_counter:
            for reason, count in reject_reason_counter.most_common(5):
                notes.append(f"硬規則淘汰主因：{reason}（{count} 檔）")

        if selector is not None and self.strategy.decision.selection_mode == "llm_assisted":
            eligible, watch_only, selection_notes, action = self._apply_llm_selection(candidate_pool, selector)
            notes.extend(selection_notes)
            selection_mode = "llm_assisted"
        else:
            eligible, watch_only, selection_notes, action = self._apply_rule_based_decision(candidate_pool)
            notes.extend(selection_notes)
            selection_mode = "rule_based"

        if not eligible:
            notes.append("今天沒有標的被列入 consider。")

        return DailyResult(
            date=self.as_of_date.isoformat(),
            strategy=self.strategy.strategy_name,
            action=action,
            selection_mode=selection_mode,
            eligible_candidates=eligible,
            watch_only_candidates=watch_only,
            notes=notes,
        )
