"""Qlib-native LLM selector — consumes Qlib signal Series directly.

Unlike the legacy `llm/selector.py` which expects `core.models.Candidate`
Pydantic objects, this module works on the native pipeline output of
Phase 10: a `pd.Series` keyed by instrument with ML scores.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import pandas as pd

from llm.openai_compat import extract_message_content, request_chat_completion

logger = logging.getLogger(__name__)


SELECTION_SYSTEM_PROMPT = """你是一位理性重視風險揭露的台股投資組合經理。

你會收到一份 Qlib 機器學習模型產出的候選清單（含 rank、score、名稱、市場）。你的工作是根據這些量化分數與用戶目前的庫存股，挑出今天最值得進一步研究的標的。

請嚴格遵守：
1. ETF 不可以因為是 ETF 就被排除；ETF 與個股都要一起比較。
2. 只能使用提供的資料（分數、ranking、庫存股、策略意圖）。不可自行補充未提供的個股資訊（如具體財報數字）。
3. verdict 只能是 consider、watch、skip。
4. consider 代表今天最值得進一步研究；watch 代表條件不完整但可觀察；skip 代表目前不優先。
5. bull_points 寫支持因素（可引用分數 ranking 或風格）；bear_points 寫保留因素；invalidation_conditions 寫何時原本成立的理由會失效。
6. 若候選與現有持股重疊或風格過度集中，必須在 portfolio_note 明確點出。
7. 最多挑 max_consider 檔為 consider、max_watch 檔為 watch，其餘 skip。
"""


_RESPONSE_SCHEMA: dict[str, Any] = {
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
                    "asset", "verdict", "confidence", "summary",
                    "bull_points", "bear_points", "invalidation_conditions",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["overall_action", "portfolio_note", "market_observation", "selections"],
    "additionalProperties": False,
}


def _decision_limits(strategy_cfg: dict) -> tuple[int, int]:
    decision = strategy_cfg.get("decision", {}) or {}
    max_consider = int(decision.get("max_consider", 5))
    max_watch = int(decision.get("max_watch", 10))
    return max_consider, max_watch


def _portfolio_tickers(portfolio_snapshot: list[dict]) -> set[str]:
    return {str(h.get("ticker", "")).strip() for h in portfolio_snapshot if h.get("ticker")}


def _signal_to_ranked_rows(
    signal: pd.Series,
    universe_meta: dict[str, dict] | None,
    top_n: int,
) -> list[dict]:
    """Convert signal Series → list of {instrument, rank, score, name, market, industry}."""
    universe_meta = universe_meta or {}
    top = signal.nlargest(top_n)
    rows: list[dict] = []
    for rank, (instrument, score) in enumerate(top.items(), start=1):
        key = str(instrument)
        meta = universe_meta.get(key) or universe_meta.get(key.split(".")[0]) or {}
        rows.append(
            {
                "instrument": key,
                "rank": rank,
                "score": float(score),
                "name": meta.get("name", key),
                "market": meta.get("market", ""),
                "industry": meta.get("industry", ""),
            }
        )
    return rows


class QlibRuleBasedSelector:
    """No-LLM selector — assigns verdicts purely by signal rank."""

    def select(
        self,
        signal: pd.Series,
        strategy_cfg: dict,
        profile_cfg: dict,
        portfolio_snapshot: list[dict],
        universe_meta: dict[str, dict] | None = None,
    ) -> dict[str, Any]:
        del profile_cfg  # unused in rule-based path
        max_consider, max_watch = _decision_limits(strategy_cfg)
        top_n = max_consider + max_watch
        rows = _signal_to_ranked_rows(signal, universe_meta, top_n)
        portfolio_set = _portfolio_tickers(portfolio_snapshot)

        selections: list[dict[str, Any]] = []
        for row in rows:
            rank = row["rank"]
            if rank <= max_consider:
                verdict = "consider"
            elif rank <= max_consider + max_watch:
                verdict = "watch"
            else:
                verdict = "skip"
            in_portfolio = row["instrument"] in portfolio_set or row["instrument"].split(".")[0] in portfolio_set
            bull = [f"模型 rank #{rank}，分數 {row['score']:.4f}"]
            bear = ["目前僅為量化分數排序，尚未做外部 LLM 深度判讀。"]
            if in_portfolio:
                bear.append("已存在於目前庫存股，需避免過度集中。")
            selections.append(
                {
                    "asset": row["instrument"],
                    "verdict": verdict,
                    "confidence": round(min(0.95, 0.5 + row["score"] / 4.0), 2),
                    "summary": f"{row['name']}（{row['market'] or '—'}）模型分數 {row['score']:.4f}，rank #{rank}。",
                    "bull_points": bull,
                    "bear_points": bear,
                    "invalidation_conditions": [
                        "若後續模型分數下降或法人轉賣，原先成立理由就可能失效。",
                    ],
                }
            )

        overlap = [r for r in rows if r["instrument"] in portfolio_set]
        if overlap:
            portfolio_note = f"候選中有 {len(overlap)} 檔與庫存股重疊：" + "、".join(r["instrument"] for r in overlap[:5])
        else:
            portfolio_note = "候選與目前庫存股未見重疊。" if portfolio_set else "目前未提供庫存股資料。"

        return {
            "overall_action": "consider" if any(s["verdict"] == "consider" for s in selections) else "hold",
            "portfolio_note": portfolio_note,
            "market_observation": "目前結果來自 Qlib 模型 ranking，尚未使用外部 LLM 深度判讀。",
            "selections": selections,
        }


class QlibLLMSelector:
    """LLM-powered selector — calls external LLM with structured JSON schema."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int = 60,
        system_prompt: str = SELECTION_SYSTEM_PROMPT,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.system_prompt = system_prompt

    def _build_payload(
        self,
        signal: pd.Series,
        strategy_cfg: dict,
        portfolio_snapshot: list[dict],
        universe_meta: dict[str, dict] | None,
    ) -> dict[str, Any]:
        max_consider, max_watch = _decision_limits(strategy_cfg)
        top_n = max_consider + max_watch
        rows = _signal_to_ranked_rows(signal, universe_meta, top_n)
        return {
            "strategy_intent": strategy_cfg.get("strategy_intent", ""),
            "selection_rules": {
                "max_consider": max_consider,
                "max_watch": max_watch,
                "selection_mode": (strategy_cfg.get("decision", {}) or {}).get("selection_mode", "llm_assisted"),
            },
            "portfolio_snapshot": [
                {
                    "ticker": h.get("ticker"),
                    "name": h.get("name"),
                    "asset_type": h.get("asset_type"),
                    "shares": h.get("shares"),
                }
                for h in portfolio_snapshot
            ],
            "candidates": rows,
        }

    def select(
        self,
        signal: pd.Series,
        strategy_cfg: dict,
        profile_cfg: dict,
        portfolio_snapshot: list[dict],
        universe_meta: dict[str, dict] | None = None,
    ) -> dict[str, Any]:
        del profile_cfg  # reserved for future per-profile overrides
        payload = self._build_payload(signal, strategy_cfg, portfolio_snapshot, universe_meta)
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
                    "name": "qlib_stock_selection",
                    "strict": True,
                    "schema": _RESPONSE_SCHEMA,
                },
            },
        }
        response = request_chat_completion(
            api_key=self.api_key,
            base_url=self.base_url,
            request_body=request_body,
            timeout=self.timeout,
            cache_namespace="qlib_selector",
            cache_key_payload={
                "model": self.model,
                "system_prompt": self.system_prompt,
                "payload": payload,
                "schema": _RESPONSE_SCHEMA,
            },
        )
        content = extract_message_content(response)
        try:
            return json.loads(content or "{}")
        except json.JSONDecodeError as exc:
            logger.warning("QlibLLMSelector: invalid JSON from LLM (%s); returning empty result", exc)
            return {"overall_action": "hold", "portfolio_note": "", "market_observation": "", "selections": []}


class QlibSelectorFactory:
    @staticmethod
    def build(provider: str | None):
        provider = (provider or os.getenv("SELECTION_PROVIDER") or os.getenv("LLM_PROVIDER") or "rule_based").strip().lower()
        if provider in {"none", "off"}:
            return None
        if provider == "rule_based":
            return QlibRuleBasedSelector()
        if provider == "groq":
            api_key = os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY")
            base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
            model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
            if not api_key:
                raise RuntimeError("GROQ_API_KEY is required for groq selector")
            return QlibLLMSelector(api_key=api_key, base_url=base_url, model=model)
        if provider == "openai_compatible":
            api_key = os.getenv("LLM_API_KEY")
            base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
            model = os.getenv("LLM_MODEL", "gpt-4o-mini")
            if not api_key:
                raise RuntimeError("LLM_API_KEY is required for openai_compatible selector")
            return QlibLLMSelector(api_key=api_key, base_url=base_url, model=model)
        raise ValueError(f"Unsupported selector provider: {provider}")
