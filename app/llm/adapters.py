"""Thin adapters wrapping legacy llm/ with Qlib-native DataFrame interface."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def select_from_signal(
    signal: pd.Series,
    profile_cfg: dict,
    top_k: int = 20,
    universe_meta: dict[str, dict] | None = None,
) -> list[dict]:
    """Run selector on a Qlib signal Series, return candidate list."""
    universe_meta = universe_meta or {}
    rows = [
        {
            "instrument": sym,
            "score": float(score),
            "name": universe_meta.get(sym, {}).get("name", sym),
            "metrics": universe_meta.get(sym, {}),
        }
        for sym, score in signal.nlargest(top_k * 3).items()
    ]
    provider = profile_cfg.get("selector_provider", "rule_based")
    try:
        from llm.selector import SelectorFactory
        SelectorFactory.build(provider)
        selected = rows[:top_k]
        return selected
    except Exception as exc:
        logger.warning("Selector %s failed: %s", provider, exc)
        return rows[:top_k]


def explain_candidates(
    candidates: list[dict],
    provider: str = "rule_based",
) -> list[dict]:
    """Add 'thesis' field to each candidate using LLM or rule-based explainer."""
    try:
        from llm.explainer import ExplainerFactory
        explainer = ExplainerFactory.build(provider)
        for c in candidates:
            payload = {
                "instrument": c.get("instrument", ""),
                "score": c.get("score", 0.0),
                "metrics": c.get("metrics", {}),
                "name": c.get("name", ""),
            }
            c["thesis"] = explainer.explain(payload)
    except Exception as exc:
        logger.warning("Explainer failed: %s", exc)
    return candidates
