"""Unit tests for app/llm/{selector,explainer,adapters}."""
from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def signal_30() -> pd.Series:
    data = {f"{2000 + i}.TW": float(30 - i) / 30.0 for i in range(30)}
    return pd.Series(data)


@pytest.fixture
def strategy_cfg() -> dict:
    return {
        "strategy_intent": "一個月左右持有，注重月營收與法人動能。",
        "decision": {"max_consider": 5, "max_watch": 10, "selection_mode": "llm_assisted"},
    }


@pytest.fixture
def profile_cfg() -> dict:
    return {"selector_provider": "rule_based", "llm_provider": "rule_based"}


@pytest.fixture
def portfolio() -> list[dict]:
    return [
        {"ticker": "2330", "name": "台積電", "asset_type": "stock", "shares": 100, "avg_cost": 500.0},
        {"ticker": "2005.TW", "name": "寶徠", "asset_type": "stock", "shares": 10, "avg_cost": 10.0},
    ]


@pytest.fixture
def universe_meta() -> dict[str, dict]:
    return {
        "2000.TW": {"name": "三洋電", "market": "TWSE", "industry": "電子"},
        "2005.TW": {"name": "寶徠", "market": "TWSE", "industry": "電子"},
    }


def test_rule_based_selector_ranks_correctly(signal_30, strategy_cfg, profile_cfg, portfolio):
    from app.llm.selector import QlibRuleBasedSelector

    out = QlibRuleBasedSelector().select(signal_30, strategy_cfg, profile_cfg, portfolio)
    assert out["overall_action"] == "consider"
    selections = out["selections"]
    assert len(selections) == 15
    assert [s["verdict"] for s in selections[:5]] == ["consider"] * 5
    assert [s["verdict"] for s in selections[5:15]] == ["watch"] * 10
    # Top-ranked should be the highest-score instrument (2000.TW)
    assert selections[0]["asset"] == "2000.TW"


def test_rule_based_selector_flags_portfolio_overlap(signal_30, strategy_cfg, profile_cfg, portfolio):
    from app.llm.selector import QlibRuleBasedSelector

    out = QlibRuleBasedSelector().select(signal_30, strategy_cfg, profile_cfg, portfolio)
    # 2005.TW is in portfolio and in top-30 candidates
    overlap_sel = next((s for s in out["selections"] if s["asset"] == "2005.TW"), None)
    assert overlap_sel is not None
    joined_bears = " ".join(overlap_sel["bear_points"])
    assert "庫存" in joined_bears
    assert "2005.TW" in out["portfolio_note"]


def test_rule_based_explainer_non_empty(signal_30, strategy_cfg, profile_cfg, portfolio):
    from app.llm.explainer import QlibRuleBasedExplainer
    from app.llm.selector import QlibRuleBasedSelector

    selector_out = QlibRuleBasedSelector().select(signal_30, strategy_cfg, profile_cfg, portfolio)
    thesis = QlibRuleBasedExplainer().explain(selector_out, signal_30, strategy_cfg, portfolio)
    assert isinstance(thesis, str)
    assert len(thesis) > 50
    assert "consider" in thesis or "觀察" in thesis
    # All consider tickers should appear in the thesis
    for sel in selector_out["selections"][:5]:
        assert sel["asset"] in thesis


def test_selector_factory_rule_based_no_api_key(monkeypatch):
    from app.llm.selector import QlibSelectorFactory, QlibRuleBasedSelector

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("SELECTION_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    selector = QlibSelectorFactory.build("rule_based")
    assert isinstance(selector, QlibRuleBasedSelector)


def test_selector_factory_groq_requires_key(monkeypatch):
    from app.llm.selector import QlibSelectorFactory

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        QlibSelectorFactory.build("groq")


def test_selector_factory_unknown_provider_raises():
    from app.llm.selector import QlibSelectorFactory

    with pytest.raises(ValueError, match="Unsupported selector provider"):
        QlibSelectorFactory.build("does_not_exist")


def test_selector_factory_none_returns_none():
    from app.llm.selector import QlibSelectorFactory

    assert QlibSelectorFactory.build("none") is None
    assert QlibSelectorFactory.build("off") is None


def test_explainer_factory_rule_based():
    from app.llm.explainer import QlibExplainerFactory, QlibRuleBasedExplainer

    explainer = QlibExplainerFactory.build("rule_based")
    assert isinstance(explainer, QlibRuleBasedExplainer)


def test_adapter_run_selection_rule_based(signal_30, strategy_cfg, profile_cfg, portfolio):
    from app.llm.adapters import run_selection

    result = run_selection(signal_30, strategy_cfg, profile_cfg, portfolio)
    assert "selections" in result
    assert len(result["selections"]) == 15


def test_adapter_run_explanation_rule_based(signal_30, strategy_cfg, profile_cfg, portfolio):
    from app.llm.adapters import run_explanation, run_selection

    selector_out = run_selection(signal_30, strategy_cfg, profile_cfg, portfolio)
    thesis = run_explanation(selector_out, signal_30, strategy_cfg, profile_cfg, portfolio)
    assert isinstance(thesis, str)
    assert len(thesis) > 30


def test_adapter_safe_mode_demotes_explainer(monkeypatch, signal_30, strategy_cfg, portfolio):
    """When both selector and explainer would use the same external LLM, demote explainer."""
    from app.llm import adapters
    from app.llm.adapters import _resolve_explainer_provider

    monkeypatch.setenv("LLM_SAFE_MODE", "true")
    profile = {"selector_provider": "groq", "llm_provider": "groq"}
    resolved = _resolve_explainer_provider(profile, selector_provider="groq")
    assert resolved == "rule_based"


def test_adapter_safe_mode_off_keeps_explainer(monkeypatch):
    from app.llm.adapters import _resolve_explainer_provider

    monkeypatch.setenv("LLM_SAFE_MODE", "false")
    profile = {"selector_provider": "groq", "llm_provider": "groq"}
    resolved = _resolve_explainer_provider(profile, selector_provider="groq")
    assert resolved == "groq"


def test_llm_selector_payload_shape(monkeypatch, signal_30, strategy_cfg, profile_cfg, portfolio, universe_meta):
    """Ensure QlibLLMSelector builds a correctly-shaped payload."""
    from app.llm.selector import QlibLLMSelector

    sel = QlibLLMSelector(api_key="fake", base_url="https://example.com", model="fake-model")
    payload = sel._build_payload(signal_30, strategy_cfg, portfolio, universe_meta)
    assert payload["strategy_intent"].startswith("一個月")
    assert payload["selection_rules"] == {"max_consider": 5, "max_watch": 10, "selection_mode": "llm_assisted"}
    assert len(payload["candidates"]) == 15
    assert payload["candidates"][0]["instrument"] == "2000.TW"
    assert payload["candidates"][0]["rank"] == 1
    assert payload["candidates"][0]["name"] == "三洋電"
    assert payload["portfolio_snapshot"][0]["ticker"] == "2330"


def test_llm_selector_calls_request_chat_completion(monkeypatch, signal_30, strategy_cfg, profile_cfg, portfolio):
    """Verify LLM selector actually invokes request_chat_completion with correct args."""
    from app.llm import selector as sel_mod

    captured: dict = {}

    def fake_request(**kwargs):
        captured.update(kwargs)
        return {
            "choices": [{"message": {"content": '{"overall_action": "consider", "portfolio_note": "test note", "market_observation": "test obs", "selections": [{"asset": "2000.TW", "verdict": "consider", "confidence": 0.8, "summary": "good", "bull_points": ["high score"], "bear_points": ["quant only"], "invalidation_conditions": ["score drop"]}]}'}}]
        }

    monkeypatch.setattr(sel_mod, "request_chat_completion", fake_request)

    llm_sel = sel_mod.QlibLLMSelector(api_key="fake-key", base_url="https://api.groq.com/openai/v1", model="test")
    out = llm_sel.select(signal_30, strategy_cfg, profile_cfg, portfolio)

    assert captured["api_key"] == "fake-key"
    assert captured["cache_namespace"] == "qlib_selector"
    assert out["selections"][0]["asset"] == "2000.TW"
    assert out["overall_action"] == "consider"
