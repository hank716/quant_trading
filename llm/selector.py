from __future__ import annotations

import json
import os
from typing import Any

from core.models import Candidate, StrategyConfig
from llm.openai_compat import extract_message_content, request_chat_completion


SELECTION_SYSTEM_PROMPT = """你是一位理性重視風險揭露的台股投資組合經理

你會收到一批由 FinMind 資料整理出的候選標的摘要。你的工作是預測價格，根據提供的資料，找出今天最值得進一步研究的標的。

請嚴格遵守：
1. ETF 不可以因為是 ETF 就被排除；ETF 與個股都要一起比較。
2. 只能使用提供的資料，不可補充外部資訊。
3. verdict 只能是 consider、watch、skip。
4. consider 代表今天最值得進一步研究；watch 代表條件不完整但可觀察；skip 代表目前不優先。
5. bull_points 要寫出支持因素；bear_points 要寫出保留因素；invalidation_conditions 要寫出何時原本成立的理由會失效。
6. 若與現有持股重疊、風格過度集中，必須明確點出。
7. 需提供買賣建議、目標價。
"""


class RuleBasedSelector:
    def _portfolio_note(self, portfolio_snapshot: dict[str, Any]) -> str:
        if not portfolio_snapshot:
            return "目前未提供庫存股資料。"
        names = []
        for stock_id, info in list(portfolio_snapshot.items())[:6]:
            names.append(f"{stock_id} {info.get('name', stock_id)}")
        return "目前庫存股包含：" + "、".join(names)

    def select(
        self,
        candidates: list[Candidate],
        strategy: StrategyConfig,
        portfolio_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        selections: list[dict[str, Any]] = []
        max_consider = strategy.decision.max_consider
        max_watch = strategy.decision.max_watch

        for idx, candidate in enumerate(candidates):
            if idx < max_consider:
                verdict = "consider"
            elif idx < max_consider + max_watch:
                verdict = "watch"
            else:
                verdict = "skip"

            invalidation = [
                item
                for item in candidate.risk[:4]
                if "庫存股" not in item and "已存在於目前庫存股" not in item
            ]
            if not invalidation:
                invalidation = ["若法人轉弱、營運動能轉差或價格結構惡化，原先理由就可能失效。"]

            summary_bits = []
            if candidate.asset_category:
                summary_bits.append(candidate.asset_category)
            if candidate.why:
                summary_bits.append("；".join(candidate.why[:2]))
            if candidate.risk:
                summary_bits.append(f"需注意：{'；'.join(candidate.risk[:2])}")

            selections.append(
                {
                    "asset": candidate.asset,
                    "verdict": verdict,
                    "confidence": round(max(0.35, min(0.95, 0.55 + candidate.score / 10.0)), 2),
                    "summary": "。".join(summary_bits) if summary_bits else "目前屬於機械式初步篩選結果。",
                    "bull_points": candidate.why[:4],
                    "bear_points": candidate.risk[:4],
                    "invalidation_conditions": invalidation,
                }
            )

        return {
            "overall_action": "consider" if any(item["verdict"] == "consider" for item in selections) else "hold",
            "portfolio_note": self._portfolio_note(portfolio_snapshot),
            "market_observation": "目前結果來自規則式預排序，尚未使用外部 LLM 深度判讀。",
            "selections": selections,
        }


class OpenAICompatibleSelector:
    RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {
            "overall_action": {"type": "string", "enum": ["consider", "hold"]},
            "portfolio_note": {"type": "string"},
            "market_observation": {"type": "string"},
            "selections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "asset": {"type": "string"},
                        "verdict": {"type": "string", "enum": ["consider", "watch", "skip"]},
                        "confidence": {"type": "number"},
                        "summary": {"type": "string"},
                        "bull_points": {"type": "array", "items": {"type": "string"}},
                        "bear_points": {"type": "array", "items": {"type": "string"}},
                        "invalidation_conditions": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "asset",
                        "verdict",
                        "confidence",
                        "summary",
                        "bull_points",
                        "bear_points",
                        "invalidation_conditions",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["overall_action", "portfolio_note", "market_observation", "selections"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int = 60,
        system_prompt: str = SELECTION_SYSTEM_PROMPT,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.system_prompt = system_prompt

    def _compact_metrics(self, metrics: dict[str, Any]) -> dict[str, Any]:
        wanted_keys = [
            "latest_close",
            "ma_value",
            "lookback_return",
            "distance_from_ma",
            "positive_flow_days",
            "total_net_buy",
            "institutional_breakdown",
            "latest_revenue_yoy_percent",
            "latest_revenue_mom_percent",
            "positive_yoy_streak_months",
            "roe_percent",
            "gross_margin_percent",
            "operating_margin_percent",
            "eps",
            "signal_breakdown",
            "ranking_score",
        ]
        return {key: metrics.get(key) for key in wanted_keys if key in metrics}

    def _build_user_payload(
        self,
        candidates: list[Candidate],
        strategy: StrategyConfig,
        portfolio_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "strategy_intent": strategy.strategy_intent,
            "selection_rules": {
                "max_consider": strategy.decision.max_consider,
                "max_watch": strategy.decision.max_watch,
                "selection_mode": strategy.decision.selection_mode,
            },
            "portfolio_snapshot": portfolio_snapshot,
            "candidates": [
                {
                    "asset": candidate.asset,
                    "name": candidate.name,
                    "asset_category": candidate.asset_category,
                    "market": candidate.market,
                    "industry": candidate.industry,
                    "score": candidate.score,
                    "why": candidate.why,
                    "risk": candidate.risk,
                    "metrics": self._compact_metrics(candidate.metrics),
                }
                for candidate in candidates
            ],
        }

    def select(
        self,
        candidates: list[Candidate],
        strategy: StrategyConfig,
        portfolio_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        payload = self._build_user_payload(candidates, strategy, portfolio_snapshot)
        request_body = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "stock_selection",
                    "strict": True,
                    "schema": self.RESPONSE_SCHEMA,
                },
            },
        }
        response_payload = request_chat_completion(
            api_key=self.api_key,
            base_url=self.base_url,
            request_body=request_body,
            timeout=self.timeout,
            cache_namespace="selector",
            cache_key_payload={
                "model": self.model,
                "system_prompt": self.system_prompt,
                "payload": payload,
                "response_schema": self.RESPONSE_SCHEMA,
            },
        )
        content = extract_message_content(response_payload)
        return json.loads(content or "{}")


class GroqSelector(OpenAICompatibleSelector):
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
            system_prompt=SELECTION_SYSTEM_PROMPT,
        )


class SelectorFactory:
    @staticmethod
    def build(provider: str | None):
        provider = (provider or os.getenv("SELECTION_PROVIDER") or os.getenv("LLM_PROVIDER") or "rule_based").strip().lower()
        if provider in {"none", "off"}:
            return None
        if provider == "rule_based":
            return RuleBasedSelector()
        if provider == "groq":
            api_key = os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY")
            base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
            model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
            if not api_key:
                raise RuntimeError("GROQ_API_KEY is required for groq selector")
            return GroqSelector(api_key=api_key, base_url=base_url, model=model)
        if provider == "openai_compatible":
            api_key = os.getenv("LLM_API_KEY")
            base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
            model = os.getenv("LLM_MODEL", "gpt-4o-mini")
            if not api_key:
                raise RuntimeError("LLM_API_KEY is required for openai_compatible selector")
            return OpenAICompatibleSelector(api_key=api_key, base_url=base_url, model=model)
        raise ValueError(f"Unsupported selector provider: {provider}")
