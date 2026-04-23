"""Qlib-native LLM explainer — turns selector output into Chinese thesis.

Consumes `QlibSelectorFactory`-produced dicts directly. No dependency on
legacy `core.models.DailyResult`.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date
from typing import Any

import pandas as pd

from llm.openai_compat import extract_message_content, request_chat_completion

logger = logging.getLogger(__name__)


EXPLAIN_SYSTEM_PROMPT = """你是一位理性重視風險揭露的台股投資組合經理。

你會收到一份來自 Qlib 模型 + selector 的結構化選股結果。請用繁體中文輸出，並嚴格遵守：
1. 先用 1 段總結今天到底該不該行動（呼應 selector 的 overall_action）。
2. 逐檔解釋 consider 與 watch 的標的為什麼會被挑出，明確引用：rank、score、bull_points / bear_points。
3. ETF 不可因為是 ETF 就被忽略。
4. 若候選與現有持股重疊，必須明確提醒（參考 portfolio_note）。
5. 最後列出「哪些情境會讓今天的判斷失效」。

- 不可自行補充未提供的個股資料（如具體財報數字）。
- 可以整理、濃縮內容，但不可改寫事實方向。
"""


def _format_portfolio(portfolio_snapshot: list[dict]) -> str:
    if not portfolio_snapshot:
        return "目前未提供庫存股資料。"
    entries: list[str] = []
    for h in portfolio_snapshot[:8]:
        ticker = h.get("ticker", "?")
        name = h.get("name", ticker)
        shares = h.get("shares")
        share_text = f"，股數 {shares}" if shares not in {None, "", 0} else ""
        entries.append(f"{ticker} {name}（{h.get('asset_type', '—')}{share_text}）")
    return "目前庫存股：" + "、".join(entries)


class QlibRuleBasedExplainer:
    """Deterministic explainer — stitches selector output into Chinese prose."""

    def explain(
        self,
        selector_output: dict[str, Any],
        signal: pd.Series,
        strategy_cfg: dict,
        portfolio_snapshot: list[dict],
    ) -> str:
        del signal  # not used in rule-based explanation
        intent = strategy_cfg.get("strategy_intent", "")
        overall = selector_output.get("overall_action", "hold")
        selections = selector_output.get("selections", [])
        portfolio_note = selector_output.get("portfolio_note", "")
        market_obs = selector_output.get("market_observation", "")

        consider = [s for s in selections if s.get("verdict") == "consider"]
        watch = [s for s in selections if s.get("verdict") == "watch"]

        parts: list[str] = []
        if intent:
            parts.append(f"策略意圖：{intent}")
        parts.append(_format_portfolio(portfolio_snapshot))
        if portfolio_note:
            parts.append(portfolio_note)
        if market_obs:
            parts.append(market_obs)

        if overall == "hold" or not consider:
            parts.append(
                "今天沒有標的被列入 consider，整體結論偏向先維持觀察。"
                "這通常代表量化模型在目前條件下仍未給出足夠強烈的訊號。"
            )
            if watch:
                watch_names = "、".join(f"{s.get('asset')}" for s in watch[:5])
                parts.append(f"仍可持續觀察的標的包括：{watch_names}。")
            parts.append("判斷失效情境：若後續模型分數提升或市場結構轉強，今天的『先觀察』結論才可能改變。")
            return "\n\n".join(parts)

        parts.append(
            f"今天模型列出 {len(consider)} 檔 consider 標的，整體動作為『{overall}』；這仍是研究輔助，不等於買賣建議。"
        )
        for idx, s in enumerate(consider, start=1):
            detail = [
                f"{idx}. {s.get('asset')}（信心 {s.get('confidence', '—')}）",
                f"- 綜合判讀：{s.get('summary', '—')}",
            ]
            bulls = s.get("bull_points", [])
            bears = s.get("bear_points", [])
            invalidation = s.get("invalidation_conditions", [])
            if bulls:
                detail.append("- 支持因素：" + "；".join(bulls[:4]))
            if bears:
                detail.append("- 保留因素：" + "；".join(bears[:4]))
            if invalidation:
                detail.append("- 失效條件：" + "；".join(invalidation[:4]))
            parts.append("\n".join(detail))

        if watch:
            watch_names = "、".join(f"{s.get('asset')}" for s in watch[:5])
            parts.append(f"另外還有僅列入 watch 的標的：{watch_names}。")

        return "\n\n".join(parts)


class QlibLLMExplainer:
    """LLM-powered explainer — returns a free-form Chinese thesis."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int = 60,
        system_prompt: str = EXPLAIN_SYSTEM_PROMPT,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.system_prompt = system_prompt

    def explain(
        self,
        selector_output: dict[str, Any],
        signal: pd.Series,
        strategy_cfg: dict,
        portfolio_snapshot: list[dict],
    ) -> str:
        selections = selector_output.get("selections", [])
        consider_count = sum(1 for s in selections if s.get("verdict") == "consider")
        payload = {
            "strategy_intent": strategy_cfg.get("strategy_intent", ""),
            "portfolio_snapshot": [
                {"ticker": h.get("ticker"), "name": h.get("name"), "shares": h.get("shares")}
                for h in portfolio_snapshot
            ],
            "selector_result": {
                "overall_action": selector_output.get("overall_action", "hold"),
                "portfolio_note": selector_output.get("portfolio_note", ""),
                "market_observation": selector_output.get("market_observation", ""),
                "selections": selections,
            },
            "signal_context": {
                "trade_date": str(date.today()),
                "model_family": "lgbm",
                "total_candidates": len(selections),
                "consider_count": consider_count,
                "signal_size": int(signal.size) if isinstance(signal, pd.Series) else 0,
            },
        }
        request_body = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
            ],
        }
        response = request_chat_completion(
            api_key=self.api_key,
            base_url=self.base_url,
            request_body=request_body,
            timeout=self.timeout,
            cache_namespace="qlib_explainer",
            cache_key_payload={
                "model": self.model,
                "system_prompt": self.system_prompt,
                "payload": payload,
            },
        )
        content = extract_message_content(response) or ""
        return content.strip()


class QlibExplainerFactory:
    @staticmethod
    def build(provider: str | None):
        provider = (provider or os.getenv("LLM_PROVIDER") or "rule_based").strip().lower()
        if provider in {"none", "off"}:
            return None
        if provider == "rule_based":
            return QlibRuleBasedExplainer()
        if provider == "groq":
            api_key = os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY")
            base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
            model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
            if not api_key:
                raise RuntimeError("GROQ_API_KEY is required for groq explainer")
            return QlibLLMExplainer(api_key=api_key, base_url=base_url, model=model)
        if provider == "openai_compatible":
            api_key = os.getenv("LLM_API_KEY")
            base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
            model = os.getenv("LLM_MODEL", "gpt-4o-mini")
            if not api_key:
                raise RuntimeError("LLM_API_KEY is required for openai_compatible explainer")
            return QlibLLMExplainer(api_key=api_key, base_url=base_url, model=model)
        raise ValueError(f"Unsupported explainer provider: {provider}")
