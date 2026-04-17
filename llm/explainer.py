from __future__ import annotations

import json
import os
from typing import Any

from core.models import DailyResult, StrategyConfig
from llm.openai_compat import extract_message_content, request_chat_completion


SYSTEM_PROMPT = """你是一位理性重視風險揭露的台股投資組合經理。

你會收到一份結構化的量化選股結果。請用繁體中文輸出，並嚴格遵守以下要求：
1. 先用 1 段總結今天到底該不該行動。
2. 再逐檔解釋候選標的為什麼會出現，必須明確提到：
   - 價格結構
   - 三大法人中到底是外資、投信、自營商誰在買或誰在賣
   - 月營收或財報中最重要的因子
3. ETF 不可因為是 ETF 就被忽略，若出現 ETF 也要正常說明。
4. 若與目前持股重疊，必須明確提醒。
5. 最後列出「哪些情境會讓今天的判斷失效」。

- 需要提供買賣建議。
- 需要預測價格。
- 不可自行補充未提供的資料。
- 可以整理與濃縮，但不可改寫事實方向。
"""


class RuleBasedExplainer:
    @staticmethod
    def _format_portfolio_snapshot(portfolio_snapshot: dict[str, Any]) -> str:
        if not portfolio_snapshot:
            return "目前未提供庫存股資訊。"
        entries: list[str] = []
        for stock_id, info in portfolio_snapshot.items():
            name = info.get("name") or stock_id
            asset_type = info.get("asset_type") or "Unknown"
            shares = info.get("shares")
            share_text = f"，股數 {shares}" if shares not in {None, ""} else ""
            entries.append(f"{stock_id} {name}（{asset_type}{share_text}）")
        return "目前庫存股：" + "、".join(entries)

    @staticmethod
    def _format_invalidation_lines(candidate: dict[str, Any]) -> str:
        metrics = candidate.get("metrics", {})
        invalidation = metrics.get("llm_invalidation_conditions") or []
        if invalidation:
            return "、".join(str(item) for item in invalidation[:4])
        raw_risks = candidate.get("risk", [])
        invalidation_risks = [item for item in raw_risks if "庫存股" not in str(item)]
        if not invalidation_risks:
            return "若法人轉弱、月營收失速、財報品質下滑或價格結構惡化，原先成立理由就可能失效。"
        return "、".join(invalidation_risks[:4])

    def explain(self, payload: dict[str, Any]) -> str:
        result = payload.get("system_result", {})
        action = result.get("action", "hold")
        candidates = result.get("candidates", [])
        watch_only = result.get("watch_only_candidates", [])
        strategy_intent = payload.get("strategy_intent", "")
        portfolio_snapshot = payload.get("portfolio_snapshot", {})
        notes = result.get("notes", [])

        intro_lines = [
            f"策略意圖：{strategy_intent}",
            self._format_portfolio_snapshot(portfolio_snapshot),
        ]

        if action == "hold" or not candidates:
            body = [
                "今天沒有標的被列入 consider，整體結論偏向先維持觀察。",
                "這通常代表：雖然市場上仍有部分標的具備單一亮點，但在價格、法人、月營收、財報與現有持股脈絡綜合評估後，仍沒有足夠完整的理由進入今天的優先研究名單。",
            ]
            if watch_only:
                watch_names = [f"{item.get('asset')} {item.get('name')}" for item in watch_only[:5]]
                body.append(f"仍可持續觀察的標的包括：{'、'.join(watch_names)}。")
            if notes:
                body.append(f"系統補充：{'；'.join(notes[:4])}。")
            body.append("判斷失效情境：若後續法人結構改善、月營收或財報更新轉強，今天的『先觀察』結論才可能改變。")
            return "\n\n".join(intro_lines + body)

        sections: list[str] = []
        sections.append(
            f"今天系統列出 {len(candidates)} 檔較值得進一步研究的標的，因此整體動作為『{action}』；這仍是研究輔助，不代表直接買賣建議。"
        )

        for idx, candidate in enumerate(candidates, start=1):
            why_items = candidate.get("why", [])
            risk_items = candidate.get("risk", [])
            metrics = candidate.get("metrics", {})
            institutional = metrics.get("institutional_breakdown", {})
            llm_summary = metrics.get("llm_summary")
            bull_points = metrics.get("llm_bull_points") or []
            bear_points = metrics.get("llm_bear_points") or []
            flow_parts: list[str] = []
            for key in ["foreign_investor", "investment_trust", "dealer"]:
                entry = institutional.get(key)
                if not entry:
                    continue
                flow_parts.append(
                    f"{entry.get('label')} {entry.get('positive_days')} 日買超、累計 {entry.get('total_net_buy')}"
                )

            revenue_yoy = metrics.get("latest_revenue_yoy_percent")
            roe = metrics.get("roe_percent")
            gross_margin = metrics.get("gross_margin_percent")
            invalidation = self._format_invalidation_lines(candidate)
            detail = [
                f"{idx}. {candidate.get('asset')} {candidate.get('name')}（{candidate.get('asset_category') or '標的'}）：",
                f"- 綜合判讀：{llm_summary or '；'.join(why_items[:3]) or '目前僅顯示為系統候選。'}",
                f"- 支持因素：{'；'.join(bull_points[:4] or why_items[:4]) if (bull_points or why_items) else '暫無額外支持因素描述。'}",
                f"- 法人拆解：{'；'.join(flow_parts) if flow_parts else '法人細項資料不足。'}",
                f"- 基本面補充：月營收年增 {revenue_yoy}%｜ROE {roe}%｜毛利率 {gross_margin}%",
                f"- 保留因素：{'；'.join(bear_points[:4] or risk_items[:4]) if (bear_points or risk_items) else '暫無額外風險註記。'}",
                f"- 失效條件：{invalidation}",
            ]
            sections.append("\n".join(detail))

        if watch_only:
            watch_names = [f"{item.get('asset')} {item.get('name')}" for item in watch_only[:5]]
            sections.append(f"另外還有一些僅列入 watch 的標的：{'、'.join(watch_names)}。")
        if notes:
            sections.append(f"系統補充：{'；'.join(notes[:6])}。")

        return "\n\n".join(intro_lines + sections)


class OpenAICompatibleExplainer:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int = 60,
        system_prompt: str = SYSTEM_PROMPT,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.system_prompt = system_prompt

    def explain(self, payload: dict[str, Any]) -> str:
        request_body = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
            ],
        }
        response_payload = request_chat_completion(
            api_key=self.api_key,
            base_url=self.base_url,
            request_body=request_body,
            timeout=self.timeout,
            cache_namespace="explainer",
            cache_key_payload={
                "model": self.model,
                "system_prompt": self.system_prompt,
                "payload": payload,
            },
        )
        return extract_message_content(response_payload)


class GroqExplainer(OpenAICompatibleExplainer):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.groq.com/openai/v1",
        model: str = "openai/gpt-oss-20b",
        timeout: int = 60,
    ):
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            system_prompt=SYSTEM_PROMPT,
        )


class ExplainerFactory:
    @staticmethod
    def build(provider: str | None):
        provider = (provider or os.getenv("LLM_PROVIDER") or "rule_based").strip().lower()
        if provider in {"none", "off"}:
            return None
        if provider == "rule_based":
            return RuleBasedExplainer()
        if provider == "groq":
            api_key = os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY")
            base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
            model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
            if not api_key:
                raise RuntimeError("GROQ_API_KEY is required for groq provider")
            return GroqExplainer(api_key=api_key, base_url=base_url, model=model)
        if provider == "openai_compatible":
            api_key = os.getenv("LLM_API_KEY")
            base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
            model = os.getenv("LLM_MODEL", "gpt-4o-mini")
            if not api_key:
                raise RuntimeError("LLM_API_KEY is required for openai_compatible provider")
            return OpenAICompatibleExplainer(api_key=api_key, base_url=base_url, model=model)
        raise ValueError(f"Unsupported LLM provider: {provider}")


class LLMExplanationAdapter:
    @staticmethod
    def build_payload(
        result: DailyResult,
        strategy: StrategyConfig,
        portfolio_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "strategy_intent": strategy.strategy_intent,
            "portfolio_snapshot": portfolio_snapshot,
            "system_result": {
                "action": result.action,
                "selection_mode": result.selection_mode,
                "candidates": [candidate.model_dump() for candidate in result.eligible_candidates],
                "watch_only_candidates": [candidate.model_dump() for candidate in result.watch_only_candidates],
                "notes": result.notes,
            },
        }
