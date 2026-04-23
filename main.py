from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False


from core.decision_engine import DecisionEngine
from core.models import ProfileConfig
from core.report_renderer import MarkdownReportRenderer
from core.strategy_loader import StrategyLoader
from core.universe import UniverseBuilder
from data.finmind_client import FinMindClient, FinMindConfig, FinMindError
from data.official_hybrid_client import OfficialHybridClient, OfficialHybridConfig
from llm.explainer import ExplainerFactory, LLMExplanationAdapter, RuleBasedExplainer
from llm.openai_compat import env_bool
from llm.selector import RuleBasedSelector, SelectorFactory
from notifications.discord_notifier import DiscordNotifier, DiscordNotifierError


def resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return base_dir / path


def split_by_stock(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if frame.empty or "stock_id" not in frame.columns:
        return {}
    frame = frame.copy()
    frame["stock_id"] = frame["stock_id"].astype(str)
    return {stock_id: group.copy() for stock_id, group in frame.groupby("stock_id")}


def compute_price_lookback(strategy) -> int:
    max_window = max(
        strategy.price_rules.ma_window,
        strategy.price_rules.lookback_days,
        strategy.institutional_flow.lookback_days,
    )
    return max(30, max_window * 3)


def compute_monthly_lookback() -> int:
    return 420


def compute_financial_lookback() -> int:
    return 900


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Personal stock screening system")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--profile-config", default=None)
    parser.add_argument("--strategy", default=None)
    parser.add_argument("--portfolio", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--markdown-output", default=None)
    parser.add_argument("--html-output", default=None) # 確保參數存在
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--stock-limit", type=int, default=None)
    parser.add_argument(
        "--stock-limit-mode",
        default="liquidity",
        choices=["stock_id", "liquidity"],
        help="stock_id=沿用代號排序前 N 檔；liquidity=盡量按最近成交金額挑前 N 檔。",
    )
    parser.add_argument("--use-mock-data", action="store_true")
    parser.add_argument("--allow-premium-batch", action="store_true")
    parser.add_argument("--cache-dir", default=os.path.join(os.getenv("CACHE_DIR", ".cache"), "finmind"))
    parser.add_argument(
        "--data-provider",
        default=os.getenv("DATA_PROVIDER", "finmind"),
        choices=["finmind", "official_hybrid"],
        help="finmind=沿用 FinMind；official_hybrid=官方日價/法人/營收 + 本地快取財報。",
    )
    parser.add_argument("--skip-discord", action="store_true")
    parser.add_argument("--force-llm-explainer", action="store_true")
    parser.add_argument(
        "--llm-provider",
        default=None,
        choices=["rule_based", "groq", "openai_compatible", "none"],
    )
    parser.add_argument(
        "--selector-provider",
        default=None,
        choices=["rule_based", "groq", "openai_compatible", "none"],
    )
    return parser.parse_args()


def resolve_profile(base_dir: Path, args: argparse.Namespace) -> tuple[ProfileConfig, Path]:
    profile_path = (
        resolve_path(base_dir, args.profile_config)
        if args.profile_config
        else base_dir / "config" / "profiles" / f"{args.profile}.yaml"
    )
    profile = StrategyLoader.load_profile(profile_path)
    return profile, profile_path


def dated_filename(prefix: str, as_of_date: date, suffix: str) -> str:
    return f"{prefix}_{as_of_date.strftime('%Y%m%d')}{suffix}"


def resolve_output_paths(
    base_dir: Path,
    args: argparse.Namespace,
    profile: ProfileConfig,
    as_of_date: date,
) -> tuple[Path, Path, Path]:
    if args.output:
        output_path = resolve_path(base_dir, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = resolve_path(base_dir, profile.output.directory)
        if profile.output.use_profile_subdirectory:
            output_dir = output_dir / profile.profile_name
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / dated_filename(profile.output.json_prefix, as_of_date, ".json")

    if args.markdown_output:
        markdown_output_path = resolve_path(base_dir, args.markdown_output)
        markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        markdown_output_path = output_path.with_name(
            dated_filename(profile.output.markdown_prefix, as_of_date, ".md")
        )
        markdown_output_path.parent.mkdir(parents=True, exist_ok=True)

    # 修正：改用 markdown_prefix 避免找不到 html_prefix 的錯誤
    if args.html_output:
        html_output_path = resolve_path(base_dir, args.html_output)
        html_output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        html_output_path = output_path.with_name(
            dated_filename(profile.output.markdown_prefix, as_of_date, ".html")
        )
        html_output_path.parent.mkdir(parents=True, exist_ok=True)

    return output_path, markdown_output_path, html_output_path

    
def select_provider(
    cli_value: str | None,
    profile_value: str | None,
    env_value: str | None,
    fallback: str,
) -> str:
    return cli_value or profile_value or env_value or fallback


def resolve_effective_explainer_provider(
    requested_provider: str,
    selector_provider: str,
    force_llm_explainer: bool,
) -> tuple[str, str | None]:
    safe_mode_enabled = env_bool("LLM_SAFE_MODE", True)
    external_providers = {"groq", "openai_compatible"}
    if force_llm_explainer or not safe_mode_enabled:
        return requested_provider, None
    if requested_provider in external_providers and selector_provider == requested_provider:
        return (
            "rule_based",
            f"LLM 安全模式已啟用：selector 已使用 {selector_provider}，為降低 rate limit，說明層自動改用 rule_based。",
        )
    return requested_provider, None


def write_outputs(result, output_path, markdown_output_path, html_output_path=None):
    from core.report_renderer import HtmlReportRenderer
    output_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    renderer = MarkdownReportRenderer()
    markdown_text = renderer.render(result)
    markdown_output_path.write_text(markdown_text, encoding="utf-8")
    if html_output_path is not None:
        html_text = HtmlReportRenderer().render(result, markdown_text)
        html_output_path.write_text(html_text, encoding="utf-8")
    return markdown_text


def rank_stock_ids_by_liquidity(
    snapshot: pd.DataFrame,
    stock_limit: int,
    portfolio_snapshot: dict[str, dict[str, object]],
) -> list[str]:
    if snapshot.empty or "stock_id" not in snapshot.columns:
        return list(portfolio_snapshot.keys())[:stock_limit]

    frame = snapshot.copy()
    frame["stock_id"] = frame["stock_id"].astype(str)
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.sort_values(["stock_id", "date"]).drop_duplicates(["stock_id"], keep="last")

    if "Trading_money" in frame.columns:
        frame["liquidity_score"] = pd.to_numeric(frame["Trading_money"], errors="coerce")
    else:
        close = pd.to_numeric(frame.get("close"), errors="coerce")
        volume = pd.to_numeric(frame.get("Trading_Volume"), errors="coerce")
        frame["liquidity_score"] = close * volume

    frame = frame.dropna(subset=["liquidity_score"]).sort_values("liquidity_score", ascending=False)
    ranked_ids = frame["stock_id"].astype(str).tolist()

    ordered: list[str] = []
    seen: set[str] = set()
    for stock_id in portfolio_snapshot.keys():
        normalized = str(stock_id)
        if normalized not in seen:
            ordered.append(normalized)
            seen.add(normalized)
    for stock_id in ranked_ids:
        if stock_id not in seen:
            ordered.append(stock_id)
            seen.add(stock_id)
        if len(ordered) >= stock_limit:
            break
    return ordered[:stock_limit]


def build_data_client(base_dir: Path, args: argparse.Namespace):
    cache_root = resolve_path(base_dir, args.cache_dir)
    if args.data_provider == "official_hybrid":
        raw_hosts = os.getenv(
            "OFFICIAL_TLS_INSECURE_FALLBACK_HOSTS",
            "mopsfin.twse.com.tw,openapi.twse.com.tw,www.tpex.org.tw",
        )
        fallback_hosts = tuple(host.strip() for host in raw_hosts.split(",") if host.strip())
        return OfficialHybridClient(
            OfficialHybridConfig(
                cache_dir=str(cache_root),
                use_mock_data=args.use_mock_data,
                finmind_token=os.getenv("FINMIND_TOKEN"),
                finmind_cache_dir=str(cache_root.parent / "finmind"),
                use_finmind_financials_cache=True,
                ssl_insecure_fallback_enabled=env_bool("OFFICIAL_TLS_INSECURE_FALLBACK", True),
                ssl_insecure_fallback_hosts=fallback_hosts,
            )
        )

    return FinMindClient(
        FinMindConfig(
            token=os.getenv("FINMIND_TOKEN"),
            cache_dir=str(cache_root),
            use_mock_data=args.use_mock_data,
            allow_batch_all_stocks=args.allow_premium_batch,
        )
    )


def build_universe(
    finmind: FinMindClient,
    as_of_date: date,
    args: argparse.Namespace,
    portfolio_snapshot: dict[str, dict[str, object]],
    pending_notes: list[str],
) -> tuple[list, date]:
    latest_trade_date = finmind.get_latest_trading_date(as_of_date)
    builder = UniverseBuilder(finmind, as_of_date)

    if args.stock_limit is None:
        if args.allow_premium_batch:
            pending_notes.append("已啟用 premium batch 模式：會優先用 FinMind 的全市場單日資料減少 API 呼叫。")
        pending_notes.append(f"本次資料對齊的最新交易日：{latest_trade_date}")
        return builder.build(), latest_trade_date

    if args.stock_limit_mode == "liquidity":
        try:
            price_snapshot = finmind.get_price_snapshot(latest_trade_date)
            preferred_stock_ids = rank_stock_ids_by_liquidity(
                price_snapshot,
                args.stock_limit,
                portfolio_snapshot,
            )
            pending_notes.append(
                f"stock-limit-mode=liquidity：以 {latest_trade_date} 最新成交金額排序挑選前 {args.stock_limit} 檔，並保留目前持股。"
            )
            pending_notes.append(f"本次資料對齊的最新交易日：{latest_trade_date}")
            return (
                builder.build(stock_limit=args.stock_limit, preferred_stock_ids=preferred_stock_ids),
                latest_trade_date,
            )
        except Exception as exc:
            pending_notes.append(
                "stock-limit-mode=liquidity 無法使用，已退回 stock_id 排序。"
                f" 原因：{exc.__class__.__name__}: {exc}"
            )

    pending_notes.append(f"stock-limit-mode=stock_id：沿用代號排序前 {args.stock_limit} 檔。")
    pending_notes.append(f"本次資料對齊的最新交易日：{latest_trade_date}")
    return builder.build(stock_limit=args.stock_limit), latest_trade_date


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    load_dotenv(base_dir / ".env.local", override=False)
    load_dotenv(base_dir / ".env", override=False)  # backward-compat fallback

    profile, profile_path = resolve_profile(base_dir, args)
    as_of_date = date.fromisoformat(args.as_of_date)

    strategy_path = resolve_path(base_dir, args.strategy or profile.strategy)
    portfolio_path = resolve_path(base_dir, args.portfolio or profile.portfolio)
    
    # 修正：接收三個回傳值，避免 ValueError
    output_path, markdown_output_path, html_output_path = resolve_output_paths(
        base_dir, args, profile, as_of_date
    )

    llm_provider = select_provider(
        args.llm_provider,
        profile.llm_provider,
        os.getenv("LLM_PROVIDER"),
        "rule_based",
    )
    selector_provider = select_provider(
        args.selector_provider,
        profile.selector_provider,
        os.getenv("SELECTION_PROVIDER") or os.getenv("LLM_PROVIDER"),
        "rule_based",
    )
    effective_llm_provider, safe_mode_note = resolve_effective_explainer_provider(
        llm_provider,
        selector_provider,
        args.force_llm_explainer,
    )

    strategy = StrategyLoader.load_strategy(strategy_path)
    portfolio_snapshot = StrategyLoader.load_portfolio(portfolio_path)
    pending_notes: list[str] = []
    if safe_mode_note:
        pending_notes.append(safe_mode_note)

    data_client = build_data_client(base_dir, args)
    if args.data_provider == "official_hybrid":
        pending_notes.append("資料源：official_hybrid（官方日價/法人/營收 + 本地快取財報）。")
    else:
        pending_notes.append("資料源：finmind。")

    universe, latest_trade_date = build_universe(
        finmind=data_client,
        as_of_date=as_of_date,
        args=args,
        portfolio_snapshot=portfolio_snapshot,
        pending_notes=pending_notes,
    )
    stock_ids = [stock.stock_id for stock in universe]

    price_end = latest_trade_date
    price_start = price_end - timedelta(days=compute_price_lookback(strategy))
    revenue_start = as_of_date - timedelta(days=compute_monthly_lookback())
    financial_start = as_of_date - timedelta(days=compute_financial_lookback())

    price_frame = data_client.get_price_history(stock_ids, price_start, price_end)
    flow_frame = data_client.get_institutional_buy_sell(stock_ids, price_start, price_end)
    revenue_frame = data_client.get_month_revenue(stock_ids, revenue_start, as_of_date)
    financial_frame = data_client.get_financial_statements(stock_ids, financial_start, as_of_date)
    if args.data_provider == "official_hybrid":
        if financial_frame.empty:
            pending_notes.append("財報資料：僅讀取本地快取；目前快取為空或尚未涵蓋候選標的，可先執行 sync_financials_slow.py。")
        else:
            pending_notes.append(f"財報資料：使用本地快取，共 {len(financial_frame)} 筆。")

    try:
        selector = SelectorFactory.build(selector_provider)
    except Exception as exc:
        if selector_provider not in {"rule_based", "none", "off"}:
            selector = RuleBasedSelector()
            pending_notes.append(
                f"LLM selector 初始化失敗，已自動退回 rule_based：{exc.__class__.__name__}: {exc}"
            )
        else:
            raise

    decision_engine = DecisionEngine(strategy, portfolio_snapshot, as_of_date)
    try:
        result = decision_engine.run(
            universe=universe,
            price_map=split_by_stock(price_frame),
            flow_map=split_by_stock(flow_frame),
            revenue_map=split_by_stock(revenue_frame),
            financial_map=split_by_stock(financial_frame),
            selector=selector,
        )
    except Exception as exc:
        if selector_provider not in {"rule_based", "none", "off"}:
            pending_notes.append(
                f"LLM selector 請求失敗，已自動退回 rule_based：{exc.__class__.__name__}: {exc}"
            )
            result = decision_engine.run(
                universe=universe,
                price_map=split_by_stock(price_frame),
                flow_map=split_by_stock(flow_frame),
                revenue_map=split_by_stock(revenue_frame),
                financial_map=split_by_stock(financial_frame),
                selector=RuleBasedSelector(),
            )
            result.selection_mode = "rule_based_fallback"
        else:
            raise

    result.generated_at = datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")
    result.profile_name = profile.profile_name
    result.profile_display_name = profile.display_name
    result.notes.extend(pending_notes)

    explanation_payload = None
    try:
        explainer = ExplainerFactory.build(effective_llm_provider)
    except Exception as exc:
        if effective_llm_provider not in {"rule_based", "none", "off"}:
            result.notes.append(
                f"LLM 說明器初始化失敗，已自動退回 rule_based：{exc.__class__.__name__}: {exc}"
            )
            explainer = RuleBasedExplainer()
        else:
            raise

    if explainer is not None:
        explanation_payload = LLMExplanationAdapter.build_payload(result, strategy, portfolio_snapshot)
        try:
            explanation = explainer.explain(explanation_payload)
        except Exception as exc:
            if effective_llm_provider not in {"rule_based", "none", "off"}:
                result.notes.append(
                    f"LLM 說明請求失敗，已自動退回 rule_based：{exc.__class__.__name__}: {exc}"
                )
                explainer = RuleBasedExplainer()
                explanation_payload = LLMExplanationAdapter.build_payload(result, strategy, portfolio_snapshot)
                explanation = explainer.explain(explanation_payload)
            else:
                raise
        result.explanation = explanation
        result.llm_payload = explanation_payload

    result.notes.extend(
        [
            f"設定檔：{profile.profile_name}（{profile.display_name}）",
            f"設定檔路徑：{profile_path}",
            f"JSON 輸出：{output_path.name}",
            f"Markdown 輸出：{markdown_output_path.name}",
            f"HTML 輸出：{html_output_path.name}",
        ]
    )

    # 修正：傳入 html_output_path
    write_outputs(result, output_path, markdown_output_path, html_output_path=html_output_path)

    discord_status = "skipped"
    if args.skip_discord:
        discord_status = "skipped_by_cli"
    else:
        notifier = DiscordNotifier(profile.discord)
        try:
            # 修正：傳入 html_path 給 notifier
            discord_info = notifier.send(
                result, 
                markdown_output_path, 
                output_path,
                html_path=html_output_path
            )
            discord_status = str(discord_info.get("status", "unknown"))
            if discord_status == "sent":
                result.notes.append("Discord webhook 已送出報告。")
            elif discord_status in {"disabled", "skipped"}:
                reason = discord_info.get("reason")
                if reason:
                    result.notes.append(f"Discord 未送出：{reason}")
        except DiscordNotifierError as exc:
            discord_status = "failed"
            result.notes.append(f"Discord 發送失敗：{exc}")
        
        if result.notes and result.notes[-1].startswith("Discord"):
            # 重新寫入以更新 notes
            write_outputs(result, output_path, markdown_output_path, html_output_path=html_output_path)

    summary = {
        "profile": profile.profile_name,
        "display_name": profile.display_name,
        "output": str(output_path),
        "markdown_output": str(markdown_output_path),
        "html_output": str(html_output_path),
        "date": result.date,
        "generated_at": result.generated_at,
        "strategy": result.strategy,
        "selection_mode": result.selection_mode,
        "action": result.action,
        "eligible_candidates": [candidate.asset for candidate in result.eligible_candidates],
        "watch_only_candidates": [candidate.asset for candidate in result.watch_only_candidates],
        "discord_status": discord_status,
        "selector_provider": selector_provider,
        "llm_provider": llm_provider,
        "effective_llm_provider": effective_llm_provider,
        "data_provider": args.data_provider,
        "stock_limit": args.stock_limit,
        "stock_limit_mode": args.stock_limit_mode,
        "latest_trade_date": latest_trade_date.isoformat(),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()