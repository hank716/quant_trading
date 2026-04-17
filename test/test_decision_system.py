from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.filter_engine import FilterEngine
from core.models import DailyResult, DiscordConfig, HardRules, UniverseStock
from core.strategy_loader import StrategyLoader
from core.signal_engine import SignalEngine
from data.finmind_client import FinMindClient, FinMindConfig
from data.official_hybrid_client import OfficialHybridClient, OfficialHybridConfig
from notifications.discord_notifier import DiscordNotifier


# --- Core logic tests ---

def test_filter_engine_rejects_new_listing() -> None:
    engine = FilterEngine(HardRules(min_listing_days=60))
    stock = UniverseStock(
        stock_id="7777",
        stock_name="NewIPO",
        market_type="emerging",
        asset_category="Stock",
        industry_category="Biotech",
        listing_days=15,
    )
    result = engine.evaluate(stock=stock, latest_price=80.0)
    assert result.passed is False
    assert any("listing_days" in reason for reason in result.reject_reasons)


def test_filter_engine_can_keep_etf_when_market_allowed() -> None:
    engine = FilterEngine(HardRules(include_markets=["twse", "tpex", "emerging", "etf"], exclude_type_keywords=[]))
    stock = UniverseStock(
        stock_id="00940",
        stock_name="Index ETF",
        market_type="etf",
        asset_category="ETF",
        industry_category="ETF",
        listing_days=200,
    )
    result = engine.evaluate(stock=stock, latest_price=10.0)
    assert result.passed is True


def test_mock_client_returns_expected_columns() -> None:
    client = FinMindClient(FinMindConfig(use_mock_data=True))
    frame = client.get_stock_info()
    assert {"stock_id", "stock_name", "industry_category", "type", "date"}.issubset(frame.columns)

    price = client.get_price_history(["2330"], pd.Timestamp("2026-01-01").date(), pd.Timestamp("2026-03-31").date())
    assert {"date", "stock_id", "close"}.issubset(price.columns)

    revenue = client.get_month_revenue(["2330"], pd.Timestamp("2025-01-01").date(), pd.Timestamp("2026-03-31").date())
    assert {"date", "stock_id", "revenue"}.issubset(revenue.columns)

    financial = client.get_financial_statements(["2330"], pd.Timestamp("2024-01-01").date(), pd.Timestamp("2026-03-31").date())
    assert {"date", "stock_id", "type", "value"}.issubset(financial.columns)


def test_signal_engine_breaks_down_investors() -> None:
    client = FinMindClient(FinMindConfig(use_mock_data=True))
    strategy = StrategyLoader.load_strategy(PROJECT_ROOT / "config/strategy_1m.yaml")
    engine = SignalEngine(strategy)

    price = client.get_price_history(["2330"], pd.Timestamp("2026-01-01").date(), pd.Timestamp("2026-03-31").date())
    flow = client.get_institutional_buy_sell(["2330"], pd.Timestamp("2026-01-01").date(), pd.Timestamp("2026-03-31").date())
    revenue = client.get_month_revenue(["2330"], pd.Timestamp("2025-01-01").date(), pd.Timestamp("2026-03-31").date())
    financial = client.get_financial_statements(["2330"], pd.Timestamp("2024-01-01").date(), pd.Timestamp("2026-03-31").date())

    result = engine.evaluate(price, flow, revenue, financial)
    breakdown = result.metrics.get("institutional_breakdown", {})
    assert set(["foreign_investor", "investment_trust", "dealer"]).issubset(breakdown.keys())
    assert result.metrics.get("latest_revenue_yoy_percent") is not None
    assert result.metrics.get("roe_percent") is not None


# --- Config/profile tests ---

def test_portfolio_loader_supports_rich_format() -> None:
    portfolio = StrategyLoader.load_portfolio(PROJECT_ROOT / "config/portfolio.yaml")
    assert portfolio["2330"]["asset_type"] == "Stock"
    assert portfolio["2330"]["shares"] == 100


def test_profile_loader_supports_multi_user() -> None:
    profile = StrategyLoader.load_profile(PROJECT_ROOT / "config/profiles/user_a.yaml")
    assert profile.profile_name == "user_a"
    assert profile.portfolio == "config/portfolio_user_a.yaml"
    assert profile.output.json_prefix == "daily_result"
    assert profile.discord.webhook_url_env == "DISCORD_WEBHOOK_URL_USER_A"


# --- Selector / provider tests ---

def test_rule_based_selector_marks_candidates() -> None:
    from llm.selector import RuleBasedSelector
    from core.models import Candidate

    selector = RuleBasedSelector()
    strategy = StrategyLoader.load_strategy(PROJECT_ROOT / "config/strategy_1m.yaml")
    candidates = [
        Candidate(asset="2330", name="TSMC", market="twse", asset_category="Stock", score=3.2, why=["A"], risk=[]),
        Candidate(asset="00940", name="Index ETF", market="etf", asset_category="ETF", score=2.4, why=["B"], risk=[]),
    ]
    result = selector.select(candidates, strategy, {})
    assert result["selections"][0]["verdict"] == "consider"
    assert result["selections"][1]["asset"] == "00940"


def test_explainer_factory_supports_groq_provider_name(monkeypatch) -> None:
    from llm.explainer import ExplainerFactory, GroqExplainer

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    explainer = ExplainerFactory.build("groq")
    assert isinstance(explainer, GroqExplainer)


def test_selector_factory_supports_groq_provider_name(monkeypatch) -> None:
    from llm.selector import GroqSelector, SelectorFactory

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    selector = SelectorFactory.build("groq")
    assert isinstance(selector, GroqSelector)


def test_resolve_effective_explainer_provider_safe_mode(monkeypatch) -> None:
    from main import resolve_effective_explainer_provider

    monkeypatch.setenv("LLM_SAFE_MODE", "true")
    provider, note = resolve_effective_explainer_provider("groq", "groq", False)
    assert provider == "rule_based"
    assert note is not None


def test_request_chat_completion_retries_and_uses_cache(monkeypatch, tmp_path: Path) -> None:
    from llm.openai_compat import request_chat_completion

    class DummyResponse:
        def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None):
            self.status_code = status_code
            self._payload = payload or {}
            self.headers = headers or {}
            self.text = json.dumps(self._payload, ensure_ascii=False)

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"status={self.status_code}")

        def json(self) -> dict:
            return self._payload

    calls = {"count": 0}

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return DummyResponse(429, {"error": "rate limited"}, headers={"Retry-After": "0"})
        return DummyResponse(200, {"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "llm-cache"))
    monkeypatch.setenv("LLM_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", "0")
    monkeypatch.setattr("llm.openai_compat.time.sleep", lambda _: None)
    monkeypatch.setattr("llm.openai_compat.requests.post", fake_post)

    payload = request_chat_completion(
        api_key="test",
        base_url="https://example.invalid/v1",
        request_body={"model": "demo", "messages": []},
        timeout=10,
        cache_namespace="unit-test",
        cache_key_payload={"demo": True},
    )
    assert payload["choices"][0]["message"]["content"] == "ok"
    assert calls["count"] == 2

    payload_cached = request_chat_completion(
        api_key="test",
        base_url="https://example.invalid/v1",
        request_body={"model": "demo", "messages": []},
        timeout=10,
        cache_namespace="unit-test",
        cache_key_payload={"demo": True},
    )
    assert payload_cached["choices"][0]["message"]["content"] == "ok"
    assert calls["count"] == 2


def test_rank_stock_ids_by_liquidity_keeps_holdings_first() -> None:
    from main import rank_stock_ids_by_liquidity

    snapshot = pd.DataFrame(
        [
            {"stock_id": "0050", "Trading_money": 1000, "date": "2026-04-17"},
            {"stock_id": "2330", "Trading_money": 9000, "date": "2026-04-17"},
            {"stock_id": "2317", "Trading_money": 7000, "date": "2026-04-17"},
        ]
    )
    ranked = rank_stock_ids_by_liquidity(snapshot, 3, {"0050": {"name": "ETF"}})
    assert ranked[0] == "0050"
    assert set(ranked) == {"0050", "2330", "2317"}


def test_mock_client_latest_trading_date() -> None:
    client = FinMindClient(FinMindConfig(use_mock_data=True))
    latest = client.get_latest_trading_date(pd.Timestamp("2026-04-18").date())
    assert latest.isoformat() == "2026-04-17"


def test_official_hybrid_mock_client_compatible() -> None:
    from data.official_hybrid_client import OfficialHybridClient, OfficialHybridConfig

    client = OfficialHybridClient(OfficialHybridConfig(use_mock_data=True))
    frame = client.get_stock_info()
    assert {"stock_id", "stock_name", "industry_category", "type", "date"}.issubset(frame.columns)

    price = client.get_price_history(["2330"], pd.Timestamp("2026-01-01").date(), pd.Timestamp("2026-03-31").date())
    assert {"date", "stock_id", "close"}.issubset(price.columns)


def test_official_hybrid_ssl_fallback_retries_insecure(monkeypatch, tmp_path: Path) -> None:
    from data.official_hybrid_client import OfficialHybridClient, OfficialHybridConfig

    client = OfficialHybridClient(
        OfficialHybridConfig(
            cache_dir=str(tmp_path / "official-cache"),
            ssl_insecure_fallback_enabled=True,
        )
    )

    class DummyResponse:
        def __init__(self, payload: list[dict[str, object]]):
            self._payload = payload
            self.text = json.dumps(payload, ensure_ascii=False)
            self.content = self.text.encode("utf-8")
            self.encoding = "utf-8"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict[str, object]]:
            return self._payload

    calls: list[bool] = []

    def fake_get(url, params=None, timeout=None, verify=True):
        calls.append(verify)
        if verify:
            raise requests.exceptions.SSLError("bad cert")
        return DummyResponse([{"公司代號": "2330", "公司名稱": "台積電", "產業別": "半導體", "上市日期": "1994/09/05"}])

    monkeypatch.setattr(client.session, "get", fake_get)
    frame = client._request_json_frame("ssl-test", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L")
    assert frame.iloc[0]["公司代號"] == "2330"
    assert calls == [True, False]


def test_official_hybrid_default_fallback_hosts_include_www_twse() -> None:
    from data.official_hybrid_client import OfficialHybridConfig

    config = OfficialHybridConfig()
    assert "www.twse.com.tw" in config.ssl_insecure_fallback_hosts


def test_official_hybrid_twse_price_json_parser(monkeypatch, tmp_path: Path) -> None:
    from data.official_hybrid_client import OfficialHybridClient, OfficialHybridConfig

    client = OfficialHybridClient(OfficialHybridConfig(cache_dir=str(tmp_path / "official-cache")))
    payload = {
        "stat": "OK",
        "fields9": ["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差"],
        "data9": [["2330", "台積電", "12,345", "678", "987,654", "950", "960", "940", "955", "+", "5"]],
    }

    monkeypatch.setattr(client, "_request_json_payload", lambda namespace, url, params=None: payload)
    monkeypatch.setattr(client, "_request_text", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected HTML fallback")))

    frame = client._fetch_twse_price_day(date(2026, 4, 17))
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["stock_id"] == "2330"
    assert row["stock_name"] == "台積電"
    assert row["close"] == 955.0
    assert row["Trading_Volume"] == 12345.0
    assert row["Trading_money"] == 987654.0
    assert row["Trading_turnover"] == 678.0


def test_official_hybrid_twse_t86_json_parser(monkeypatch, tmp_path: Path) -> None:
    from data.official_hybrid_client import OfficialHybridClient, OfficialHybridConfig

    client = OfficialHybridClient(OfficialHybridConfig(cache_dir=str(tmp_path / "official-cache")))
    payload = {
        "stat": "OK",
        "fields": [
            "證券代號",
            "證券名稱",
            "外陸資買進股數(不含外資自營商)",
            "外陸資賣出股數(不含外資自營商)",
            "外陸資買賣超股數(不含外資自營商)",
            "外資自營商買進股數",
            "外資自營商賣出股數",
            "外資自營商買賣超股數",
            "投信買進股數",
            "投信賣出股數",
            "投信買賣超股數",
            "自營商買賣超股數",
            "自營商買進股數(自行買賣)",
            "自營商賣出股數(自行買賣)",
            "自營商買賣超股數(自行買賣)",
            "自營商買進股數(避險)",
            "自營商賣出股數(避險)",
            "自營商買賣超股數(避險)",
            "三大法人買賣超股數",
        ],
        "data": [["2330", "台積電", "1,000", "400", "600", "0", "0", "0", "200", "50", "150", "45", "20", "5", "15", "100", "70", "30", "795"]],
    }

    monkeypatch.setattr(client, "_request_json_payload", lambda namespace, url, params=None: payload)
    monkeypatch.setattr(client, "_request_text", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected HTML fallback")))

    frame = client._fetch_twse_institutional_day(date(2026, 4, 17))
    assert set(frame["name"]) == {"Foreign_Investor", "Investment_Trust", "Dealer_Hedging"}
    foreign = frame[frame["name"] == "Foreign_Investor"].iloc[0]
    trust = frame[frame["name"] == "Investment_Trust"].iloc[0]
    dealer = frame[frame["name"] == "Dealer_Hedging"].iloc[0]
    assert foreign["buy"] == 1000.0 and foreign["sell"] == 400.0
    assert trust["buy"] == 200.0 and trust["sell"] == 50.0
    assert dealer["buy"] == 120.0 and dealer["sell"] == 75.0


def test_official_hybrid_tpex_price_csv_parser_handles_preamble(monkeypatch, tmp_path: Path) -> None:
    from data.official_hybrid_client import OfficialHybridClient, OfficialHybridConfig

    client = OfficialHybridClient(OfficialHybridConfig(cache_dir=str(tmp_path / "official-cache")))
    sample_csv = (
        '上櫃股票每日收盤行情(不含定價)\n'
        '資料日期:115/04/17\n'
        '\n'
        '"代號","名稱","收盤","漲跌","開盤","最高","最低","成交股數","成交金額(元)","成交筆數","最後買價","最後買量(張數)","最後賣價","最後賣量(張數)","發行股數","次日漲停價","次日跌停價"\n'
        '"3324","雙鴻","510.00","+5.00","505.00","512.00","500.00","1,234,567","890,123,456","1,234","509.00","5","510.00","2","98,765,432","561.00","459.00"\n'
        '共1筆\n'
        '註：測試說明\n'
    )

    monkeypatch.setattr(client, "_request_text", lambda *args, **kwargs: sample_csv)
    frame = client._fetch_tpex_price_day(date(2026, 4, 17))
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["stock_id"] == "3324"
    assert row["stock_name"] == "雙鴻"
    assert row["close"] == 510.0
    assert row["Trading_Volume"] == 1234567.0
    assert row["Trading_money"] == 890123456.0


def test_official_hybrid_tpex_inst_csv_parser_handles_preamble(monkeypatch, tmp_path: Path) -> None:
    from data.official_hybrid_client import OfficialHybridClient, OfficialHybridConfig

    client = OfficialHybridClient(OfficialHybridConfig(cache_dir=str(tmp_path / "official-cache")))
    sample_csv = (
        '三大法人買賣明細資訊\n'
        '資料日期:115/04/17\n'
        '\n'
        '"代號","名稱","外資及陸資(不含外資自營商)-買進股數","外資及陸資(不含外資自營商)-賣出股數","外資及陸資(不含外資自營商)-買賣超股數","投信-買進股數","投信-賣出股數","投信-買賣超股數","自營商(自行買賣)-買進股數","自營商(自行買賣)-賣出股數","自營商(自行買賣)-買賣超股數","自營商(避險)-買進股數","自營商(避險)-賣出股數","自營商(避險)-買賣超股數","自營商-買賣超股數","三大法人買賣超股數合計"\n'
        '"3324","雙鴻","1,000","600","400","300","100","200","50","10","40","70","20","50","90","690"\n'
        '共1筆\n'
    )

    monkeypatch.setattr(client, "_request_text", lambda *args, **kwargs: sample_csv)
    frame = client._fetch_tpex_institutional_day(date(2026, 4, 17))
    assert set(frame["name"]) == {"Foreign_Investor", "Investment_Trust", "Dealer_Hedging"}
    foreign = frame[frame["name"] == "Foreign_Investor"].iloc[0]
    trust = frame[frame["name"] == "Investment_Trust"].iloc[0]
    dealer = frame[frame["name"] == "Dealer_Hedging"].iloc[0]
    assert foreign["buy"] == 1000.0 and foreign["sell"] == 600.0
    assert trust["buy"] == 300.0 and trust["sell"] == 100.0
    assert dealer["buy"] == 120.0 and dealer["sell"] == 30.0


def test_main_official_hybrid_mock_generates_output(tmp_path: Path) -> None:
    output_dir = tmp_path / "out_official"
    profile_path = tmp_path / "profile_official.yaml"
    profile_payload = {
        "profile_name": "official_tester",
        "display_name": "官方資料測試",
        "strategy": "config/strategy_1m.yaml",
        "portfolio": "config/portfolio.yaml",
        "selector_provider": "rule_based",
        "llm_provider": "rule_based",
        "output": {
            "directory": str(output_dir),
            "use_profile_subdirectory": True,
            "json_prefix": "daily_result",
            "markdown_prefix": "daily_report",
        },
        "discord": {"enabled": False},
    }
    profile_path.write_text(yaml.safe_dump(profile_payload, allow_unicode=True), encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "main.py"),
            "--profile-config",
            str(profile_path),
            "--data-provider",
            "official_hybrid",
            "--use-mock-data",
            "--as-of-date",
            "2026-04-17",
            "--skip-discord",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )

    json_path = output_dir / "official_tester" / "daily_result_20260417.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert any("official_hybrid" in note for note in payload["notes"])


# --- Discord tests ---

def test_discord_notifier_builds_content() -> None:
    notifier = DiscordNotifier(
        DiscordConfig(enabled=True, webhook_url="https://example.invalid", username="Test Bot")
    )
    result = DailyResult(
        date="2026-04-17",
        generated_at="2026-04-17T10:00:00+08:00",
        profile_name="user_a",
        profile_display_name="使用者 A",
        strategy="demo_strategy",
        action="consider",
        eligible_candidates=[],
        watch_only_candidates=[],
    )
    content = notifier.build_message_content(result, markdown_text="# 每日選股報告\n\n內容")
    assert "每日選股報告" in content
    assert "使用者 A" in content
    assert "2026-04-17" in content


# --- CLI / output tests ---

def test_main_generates_dated_output_with_profile(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.yaml"
    profile_payload = {
        "profile_name": "tester",
        "display_name": "測試使用者",
        "strategy": "config/strategy_1m.yaml",
        "portfolio": "config/portfolio.yaml",
        "selector_provider": "rule_based",
        "llm_provider": "rule_based",
        "output": {
            "directory": str(output_dir),
            "use_profile_subdirectory": True,
            "json_prefix": "daily_result",
            "markdown_prefix": "daily_report",
        },
        "discord": {
            "enabled": False,
            "webhook_url_env": "DISCORD_WEBHOOK_URL_TESTER",
        },
    }
    profile_path.write_text(yaml.safe_dump(profile_payload, allow_unicode=True), encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "main.py"),
            "--profile-config",
            str(profile_path),
            "--use-mock-data",
            "--as-of-date",
            "2026-04-17",
            "--skip-discord",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )

    json_path = output_dir / "tester" / "daily_result_20260417.json"
    markdown_path = output_dir / "tester" / "daily_report_20260417.md"
    assert json_path.exists()
    assert markdown_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert payload["profile_name"] == "tester"
    assert payload["profile_display_name"] == "測試使用者"
    assert payload["date"] == "2026-04-17"
    assert payload["generated_at"]
    assert "daily_result_20260417.json" in payload["notes"][-2]
    assert "設定檔" in markdown
    assert "測試使用者" in markdown
    assert "2026-04-17" in markdown
    assert "## Consider 候選" in markdown
    assert "## Watch 名單" in markdown


def test_official_hybrid_twse_price_json_only_no_html_on_empty_payload(monkeypatch, tmp_path: Path) -> None:
    from data.official_hybrid_client import OfficialHybridClient, OfficialHybridConfig

    client = OfficialHybridClient(OfficialHybridConfig(cache_dir=str(tmp_path / "official-cache")))
    payload = {"stat": "很抱歉，沒有符合條件的資料!"}

    monkeypatch.setattr(client, "_request_json_payload", lambda namespace, url, params=None: payload)
    monkeypatch.setattr(client, "_request_text", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected HTML fallback")))

    frame = client._fetch_twse_price_day(date(2026, 4, 19))
    assert frame.empty


def test_official_hybrid_twse_t86_json_only_no_html_on_empty_payload(monkeypatch, tmp_path: Path) -> None:
    from data.official_hybrid_client import OfficialHybridClient, OfficialHybridConfig

    client = OfficialHybridClient(OfficialHybridConfig(cache_dir=str(tmp_path / "official-cache")))
    payload = {"stat": "很抱歉，沒有符合條件的資料!"}

    monkeypatch.setattr(client, "_request_json_payload", lambda namespace, url, params=None: payload)
    monkeypatch.setattr(client, "_request_text", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected HTML fallback")))

    frame = client._fetch_twse_institutional_day(date(2026, 4, 19))
    assert frame.empty


def test_get_price_snapshot_returns_empty_frame_on_non_trading_day(monkeypatch, tmp_path):
    client = OfficialHybridClient(OfficialHybridConfig(cache_dir=str(tmp_path)))
    monkeypatch.setattr(client, "_fetch_twse_price_day", lambda _day: pd.DataFrame())
    monkeypatch.setattr(client, "_fetch_tpex_price_day", lambda _day: pd.DataFrame())

    frame = client.get_price_snapshot(date(2026, 4, 18))

    assert isinstance(frame, pd.DataFrame)
    assert frame.empty
    assert list(frame.columns) == [
        "stock_id",
        "stock_name",
        "date",
        "close",
        "Trading_Volume",
        "Trading_money",
        "open",
        "max",
        "min",
        "Trading_turnover",
        "market_type",
    ]


def test_get_institutional_buy_sell_skips_empty_days(monkeypatch, tmp_path):
    client = OfficialHybridClient(OfficialHybridConfig(cache_dir=str(tmp_path)))
    monkeypatch.setattr(client, "_fetch_twse_institutional_day", lambda _day: pd.DataFrame())
    monkeypatch.setattr(client, "_fetch_tpex_institutional_day", lambda _day: pd.DataFrame())

    frame = client.get_institutional_buy_sell(["2330"], date(2026, 4, 18), date(2026, 4, 19))

    assert isinstance(frame, pd.DataFrame)
    assert frame.empty


def test_official_hybrid_normalizes_listing_dates(monkeypatch, tmp_path: Path) -> None:
    from data.official_hybrid_client import OfficialHybridClient, OfficialHybridConfig

    client = OfficialHybridClient(OfficialHybridConfig(cache_dir=str(tmp_path / "official-cache")))
    listed_frame = pd.DataFrame([
        {"公司代號": "1101", "公司名稱": "臺灣水泥股份有限公司", "產業別": "水泥工業", "上市日期": "19620209"},
    ])
    otc_frame = pd.DataFrame([
        {"公司代號": "5483", "公司名稱": "中美晶", "產業別": "半導體業", "上櫃日期": "83/12/05"},
    ])

    monkeypatch.setattr(client, "_request_json_frame", lambda *args, **kwargs: listed_frame)
    monkeypatch.setattr(client, "_request_csv_frame", lambda *args, **kwargs: otc_frame)

    frame = client.get_stock_info().sort_values("stock_id").reset_index(drop=True)
    assert frame.loc[0, "date"] == "1962-02-09"
    assert frame.loc[1, "date"] == "1994-12-05"


def test_finmind_client_reads_cached_financial_statements(tmp_path: Path) -> None:
    cache_dir = tmp_path / "finmind-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"date": "2025-03-31", "stock_id": "2330", "type": "ROE", "value": 20.0},
            {"date": "2025-03-31", "stock_id": "2330", "type": "營業毛利率", "value": 50.0},
            {"date": "2025-03-31", "stock_id": "2317", "type": "ROE", "value": 10.0},
        ]
    ).to_json(cache_dir / "TaiwanStockFinancialStatements_test.json", orient="records", force_ascii=False)

    client = FinMindClient(FinMindConfig(cache_dir=str(cache_dir)))
    frame = client.get_cached_financial_statements(["2330"], pd.Timestamp("2024-01-01").date(), pd.Timestamp("2026-04-17").date())
    assert set(frame["stock_id"]) == {"2330"}
    assert set(frame["type"]) == {"ROE", "營業毛利率"}


def test_official_hybrid_reads_financials_from_cache_only(tmp_path: Path) -> None:
    finmind_cache = tmp_path / "finmind-cache"
    finmind_cache.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"date": "2025-12-31", "stock_id": "2330", "type": "ROE", "value": 25.0},
            {"date": "2025-12-31", "stock_id": "2330", "type": "營業毛利率", "value": 53.0},
        ]
    ).to_json(finmind_cache / "TaiwanStockFinancialStatements_cached.json", orient="records", force_ascii=False)

    client = OfficialHybridClient(
        OfficialHybridConfig(
            cache_dir=str(tmp_path / "official-cache"),
            finmind_cache_dir=str(finmind_cache),
            use_finmind_financials_cache=True,
        )
    )
    frame = client.get_financial_statements(["2330"], pd.Timestamp("2024-01-01").date(), pd.Timestamp("2026-04-17").date())
    assert not frame.empty
    assert set(frame["stock_id"]) == {"2330"}


def test_sync_financials_slow_mock_advances_cursor(tmp_path: Path) -> None:
    cursor_path = tmp_path / "cursor.json"
    cache_dir = tmp_path / "finmind-cache"
    official_cache_dir = tmp_path / "official-cache"

    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "sync_financials_slow.py"),
            "--use-mock-data",
            "--batch-size",
            "3",
            "--cursor-file",
            str(cursor_path),
            "--cache-dir",
            str(cache_dir),
            "--official-cache-dir",
            str(official_cache_dir),
            "--as-of-date",
            "2026-04-17",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["mode"] == "financial_slow_sync"
    assert payload["selected_count"] == 3
    assert cursor_path.exists()
    cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
    assert cursor["next_index"] == 3
