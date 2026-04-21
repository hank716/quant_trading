# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Personal Taiwan stock screening system that performs daily analysis of TWSE/TPEx markets to identify investment candidates using rule-based filtering, quantitative signals, and optional LLM-assisted selection and explanation.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest -q

# Run a single test file
pytest test/test_decision_system.py -v

# Test with mock data (no API calls, no Discord)
python main.py --profile user_a --use-mock-data --skip-discord

# Sync daily market data to local cache (run before main.py)
python sync_data.py --profile user_a --data-provider official_hybrid --lookback-days 35

# Sync financial statements slowly (run periodically, respects quotas)
python sync_financials_slow.py --batch-size 30

# Full run with official data
python main.py --profile user_a --data-provider official_hybrid --stock-limit 100 --stock-limit-mode liquidity --skip-discord
```

**Key `main.py` flags:**
- `--profile {default|user_a|user_b}` — selects user config, portfolio, and Discord webhook
- `--as-of-date YYYY-MM-DD` — backtest / historical run (defaults to today)
- `--selector-provider {rule_based|groq|openai_compatible}` — overrides profile's LLM selector
- `--llm-provider {rule_based|groq|openai_compatible}` — overrides profile's explainer LLM
- `--force-llm-explainer` — bypasses safe mode to use LLM for explanation

## Architecture

### Pipeline (main.py → DecisionEngine)

```
UniverseBuilder         → ~2000 Taiwan stocks/ETFs, ranked by trading volume
  ↓
Data fetch (parallel)   → price history, institutional flows, monthly revenue, financials
  ↓
For each stock:
  FilterEngine          → hard rules (market type, listing age, price floor, keyword exclusions)
  SignalEngine          → quantitative signals (MA, 20-day return, inst. flows, revenue YoY, ROE)
  ↓
SelectorFactory         → RuleBasedSelector (deterministic rank) OR LLM selector (Groq/OpenAI)
  ↓
ExplainerFactory        → RuleBasedExplainer OR LLM explainer (Chinese-language thesis)
  ↓
ReportRenderer          → Markdown + HTML reports + JSON result
DiscordNotifier         → webhook with report attachments
```

### Key modules

| Path | Responsibility |
|------|---------------|
| `core/decision_engine.py` | Orchestrates filter → signal → select pipeline |
| `core/filter_engine.py` | Hard rules (market, keywords, price, listing days) |
| `core/signal_engine.py` | Quantitative signals (price action, inst. flows, revenue, financials) |
| `core/models.py` | Pydantic models: `HardRules`, `SignalResult`, `Candidate`, `DailyResult` |
| `core/universe.py` | Fetches metadata for all stocks; optionally ranks by liquidity |
| `core/strategy_loader.py` | Parses strategy, profile, and portfolio YAML files |
| `core/report_renderer.py` | Markdown and HTML report generation |
| `data/official_hybrid_client.py` | Primary data client: official TWSE/TPEx JSON/CSV + cached financials |
| `data/finmind_client.py` | Alternative data client with MD5-keyed response cache |
| `llm/selector.py` | Rule-based and LLM candidate selection |
| `llm/explainer.py` | Rule-based and LLM explanation generation |
| `llm/openai_compat.py` | OpenAI-compatible API abstraction with retry, rate-limit, and response caching |
| `notifications/discord_notifier.py` | Discord webhook with file attachment support |

### Configuration hierarchy

```
config/strategy_1m.yaml          ← hard rules, signal thresholds, selection limits
config/profiles/{profile}.yaml   ← user's strategy, portfolio, LLM provider, output dir, Discord
config/portfolio_{profile}.yaml  ← current holdings (for overlap warnings)
.env                             ← secrets: API tokens, webhook URLs, LLM keys
```

Profiles reference a strategy file and a portfolio file. The `--profile` flag is how you switch between users.

### LLM safe mode

When `LLM_SAFE_MODE=true` (default) and both selector and explainer are configured to the same external LLM (e.g., both Groq), the explainer is automatically demoted to `rule_based` to halve API calls. This is logged in `result.notes`. Use `--force-llm-explainer` to override.

LLM responses are cached to `.cache/llm/` by SHA256 of the request payload, so identical requests never re-hit the API.

### Data sources

`official_hybrid` (recommended): daily prices, institutional flows, and monthly revenue come from official TWSE/TPEx endpoints; financial statements come exclusively from the local cache built by `sync_financials_slow.py`. The `finmind` provider uses the FinMind API for everything (higher quota cost).

Financial statements are **never live-fetched** in `main.py` — run `sync_financials_slow.py` periodically to keep the cache current.

### Output

Each run writes to `outputs/{profile}/`:
- `daily_result_YYYYMMDD.json` — full structured result with candidates, metrics, and notes
- `daily_report_YYYYMMDD.md` — human-readable Markdown report
- `daily_report_YYYYMMDD.html` — styled HTML version

## Environment Variables

See `env.example` for the full reference. Critical ones:

```dotenv
FINMIND_TOKEN=           # Required if using finmind data provider
DATA_PROVIDER=official_hybrid
GROQ_API_KEY=            # Required if using groq LLM provider
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=openai/gpt-oss-20b
DISCORD_WEBHOOK_URL_USER_A=
OFFICIAL_TLS_INSECURE_FALLBACK=true   # Set if TWSE/TPEx TLS errors occur
```
