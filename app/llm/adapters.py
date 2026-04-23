"""Thin orchestration wrappers for the Qlib-native selector/explainer.

Called by `app/orchestration/run_daily.py`. Handles provider resolution
and the `LLM_SAFE_MODE` demotion of the explainer when both selector and
explainer use the same external LLM.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import pandas as pd

from app.llm.explainer import QlibExplainerFactory, QlibLLMExplainer
from app.llm.selector import QlibLLMSelector, QlibSelectorFactory

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_selector_provider(profile_cfg: dict) -> str:
    return (
        profile_cfg.get("selector_provider")
        or os.getenv("SELECTION_PROVIDER")
        or os.getenv("LLM_PROVIDER")
        or "rule_based"
    ).strip().lower()


def _resolve_explainer_provider(profile_cfg: dict, selector_provider: str) -> str:
    explainer = (
        profile_cfg.get("llm_provider")
        or os.getenv("LLM_PROVIDER")
        or "rule_based"
    ).strip().lower()
    external = {"groq", "openai_compatible"}
    if _env_bool("LLM_SAFE_MODE", True) and explainer in external and explainer == selector_provider:
        logger.info("LLM_SAFE_MODE: demoting explainer from %s to rule_based (same provider as selector)", explainer)
        return "rule_based"
    return explainer


def run_selection(
    signal: pd.Series,
    strategy_cfg: dict,
    profile_cfg: dict,
    portfolio_snapshot: list[dict],
    universe_meta: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Build selector for the resolved provider and invoke `.select(...)`."""
    provider = _resolve_selector_provider(profile_cfg)
    try:
        selector = QlibSelectorFactory.build(provider)
    except Exception as exc:
        logger.warning("Selector build failed (%s); falling back to rule_based: %s", provider, exc)
        selector = QlibSelectorFactory.build("rule_based")
        provider = "rule_based"
    if selector is None:
        logger.info("Selector provider is 'none'; returning empty hold result")
        return {"overall_action": "hold", "portfolio_note": "", "market_observation": "", "selections": []}
    llm_call = isinstance(selector, QlibLLMSelector)
    logger.info("Selector: %s (llm_call=%s)", provider, llm_call)
    try:
        result = selector.select(signal, strategy_cfg, profile_cfg, portfolio_snapshot, universe_meta)
    except Exception as exc:
        logger.warning("Selector.select() failed with %s (%s); falling back to rule_based", provider, exc)
        fallback = QlibSelectorFactory.build("rule_based")
        result = fallback.select(signal, strategy_cfg, profile_cfg, portfolio_snapshot, universe_meta)
    logger.info("Selector returned %d selections", len(result.get("selections", [])))
    return result


def run_explanation(
    selector_output: dict[str, Any],
    signal: pd.Series,
    strategy_cfg: dict,
    profile_cfg: dict,
    portfolio_snapshot: list[dict],
) -> str:
    """Build explainer (honouring LLM_SAFE_MODE) and invoke `.explain(...)`."""
    selector_provider = _resolve_selector_provider(profile_cfg)
    provider = _resolve_explainer_provider(profile_cfg, selector_provider)
    try:
        explainer = QlibExplainerFactory.build(provider)
    except Exception as exc:
        logger.warning("Explainer build failed (%s); falling back to rule_based: %s", provider, exc)
        explainer = QlibExplainerFactory.build("rule_based")
        provider = "rule_based"
    if explainer is None:
        return ""
    llm_call = isinstance(explainer, QlibLLMExplainer)
    logger.info("Explainer: %s (llm_call=%s)", provider, llm_call)
    try:
        return explainer.explain(selector_output, signal, strategy_cfg, portfolio_snapshot)
    except Exception as exc:
        logger.warning("Explainer.explain() failed with %s (%s); returning empty string", provider, exc)
        return ""
