# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Personal Taiwan stock screening system. Daily pipeline analyzes TWSE/TPEx markets (~2000 stocks), applies rule-based filters and quantitative signals, and outputs investment candidates with explanations. Infrastructure uses Docker + Supabase + pCloud, with a Streamlit control UI and Grafana dashboards.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests (unit only, no external deps)
pytest -q -m "not integration"

# Run all tests including integration
pytest -q

# Test with mock data (no API calls, no Discord)
python main.py --profile user_a --use-mock-data --skip-discord

# Sync daily market data to local cache
python sync_data.py --profile user_a --data-provider official_hybrid --lookback-days 35

# Sync financial statements (run periodically, respects quotas)
python sync_financials_slow.py --batch-size 30

# Full run with official data
python main.py --profile user_a --data-provider official_hybrid --stock-limit 100 --stock-limit-mode liquidity --skip-discord

# Apply Supabase schema (requires DATABASE_URL)
bash scripts/linux/apply_schema.sh
```

**Key `main.py` flags:**
- `--profile {default|user_a|user_b}` — selects user config, portfolio, and Discord webhook
- `--as-of-date YYYY-MM-DD` — backtest / historical run (defaults to today)
- `--selector-provider {rule_based|groq|openai_compatible}` — overrides profile's LLM selector
- `--llm-provider {rule_based|groq|openai_compatible}` — overrides profile's explainer LLM
- `--force-llm-explainer` — bypasses safe mode to use LLM for explanation

## Architecture

### Full Pipeline

```
UniverseBuilder          → ~2000 Taiwan stocks/ETFs, ranked by trading volume
  ↓
Data fetch (parallel)    → price history, institutional flows, monthly revenue, financials
  ↓
FilterEngine             → hard rules: market type, listing age, price floor, keyword exclusions
SignalEngine             → quantitative signals: MA, 20-day return, inst. flows, revenue YoY, ROE
  ↓
SelectorFactory          → RuleBasedSelector OR LLM selector (Groq/OpenAI-compat)
ExplainerFactory         → RuleBasedExplainer OR LLM explainer (Chinese-language thesis)
  ↓
ArtifactWriter           → signals.parquet, positions.parquet, trades.parquet, report.json, manifest.json
  ↓
SupabaseClient           → insert pipeline_run, register artifacts, insert candidates
  ↓
PCloudClient             → upload artifacts to /reports/date={date}/run_id={run_id}/
  ↓
ReportRenderer           → Markdown + HTML reports
DiscordNotifier          → webhook with report attachments
```

### Module Map

| Path | Responsibility |
|------|---------------|
| `core/decision_engine.py` | Orchestrates filter → signal → select pipeline |
| `core/filter_engine.py` | Hard rules (market, keywords, price, listing days) |
| `core/signal_engine.py` | Quantitative signals (price action, inst. flows, revenue, financials) |
| `core/models.py` | Pydantic models: `HardRules`, `SignalResult`, `Candidate`, `DailyResult` |
| `core/universe.py` | Fetches metadata for all stocks; optionally ranks by liquidity |
| `core/strategy_loader.py` | Parses strategy, profile, and portfolio YAML files |
| `core/report_renderer.py` | Markdown and HTML report generation |
| `data/official_hybrid_client.py` | Primary data: TWSE/TPEx JSON/CSV + cached financials |
| `data/finmind_client.py` | Alternative data client with MD5-keyed response cache |
| `llm/selector.py` | Rule-based and LLM candidate selection |
| `llm/explainer.py` | Rule-based and LLM explanation generation |
| `llm/openai_compat.py` | OpenAI-compatible API abstraction with retry, rate-limit, response caching |
| `notifications/discord_notifier.py` | Discord webhook with file attachment support |
| `src/orchestration/run_daily.py` | Daily pipeline entry point: artifacts + DB writes |
| `src/database/client.py` | Supabase wrapper with mock fallback |
| `src/database/crud.py` | PipelineRunCRUD, ArtifactCRUD, CandidateCRUD, CoverageCRUD |
| `src/database/schema.sql` | Supabase schema: 11 tables + indexes |
| `src/storage/artifact_writer.py` | Writes parquet/json artifacts to workspace/runs/{run_id}/ |
| `src/storage/pcloud_client.py` | pCloud API wrapper with mock fallback |
| `src/reporting/converter.py` | DailyResult → artifact schemas converter |
| `src/ui/app.py` | Streamlit UI: Home / Runs / 庫存股 / Coverage / Reports / Run Control |

### Directory Structure

```
fin/
├── core/           ← existing decision engine (preserve, gradually migrate to src/)
├── data/           ← data clients (official_hybrid, finmind)
├── llm/            ← selector, explainer, openai_compat
├── notifications/  ← discord notifier
├── config/         ← strategy YAML, profiles, portfolios
├── src/
│   ├── orchestration/   ← run_daily.py, run_signal.py, run_report.py
│   ├── database/        ← client.py, crud.py, schema.sql
│   ├── storage/         ← pcloud_client.py, artifact_writer.py
│   ├── reporting/       ← schema.py, converter.py
│   ├── signals/         ← schema.py (Phase 5: labeler, trainer, predictor)
│   ├── features/        ← (Phase 5: tech_features, fund_features, feature_builder)
│   ├── registry/        ← (Phase 5: model_registry, retrain_gate)
│   ├── monitoring/      ← (Phase 4: coverage_checker)
│   └── ui/              ← app.py
├── tests/
│   ├── unit/            ← fast tests, no external deps
│   ├── contract/        ← schema validation
│   └── integration/     ← require Docker or credentials (@pytest.mark.integration)
├── docker/         ← app.Dockerfile, ui.Dockerfile
├── compose/        ← docker-compose.yml, prometheus.yml, grafana provisioning
├── scripts/        ← linux/ and windows/ run/start scripts
├── docs/           ← setup guides, ADRs, env reference, work log
├── workspace/      ← runtime data (gitignored): hotdata, runs, outputs, logs, tmp
└── main.py         ← legacy entry point (compatibility layer)
```

### Configuration Hierarchy

```
config/strategy_1m.yaml          ← hard rules, signal thresholds, selection limits
config/profiles/{profile}.yaml   ← user's strategy, portfolio, LLM provider, output dir, Discord
config/portfolio_{profile}.yaml  ← current holdings (shown in Streamlit UI, editable)
.env.local                       ← secrets: API tokens, webhook URLs, LLM keys (gitignored)
```

### LLM Safe Mode

When `LLM_SAFE_MODE=true` (default) and both selector and explainer use the same external LLM, the explainer auto-demotes to `rule_based` to halve API calls. Use `--force-llm-explainer` to override.

LLM responses are cached to `.cache/llm/` by SHA256 of the request payload.

### Data Sources

`official_hybrid` (recommended): daily prices, institutional flows, monthly revenue from official TWSE/TPEx endpoints. Financial statements from local cache built by `sync_financials_slow.py` only — never live-fetched in `main.py`.

### Artifact Storage

Each run writes to `workspace/runs/{run_id}/`:
- `signals.parquet`, `positions.parquet`, `trades.parquet`
- `report.json`, `manifest.json`

Run state is tracked in Supabase `pipeline_runs` table. Artifacts are uploaded to pCloud at `/reports/date={date}/run_id={run_id}/`.

## Git Workflow

```
main     ← protected, never push directly, only manual review merges here
develop  ← integration branch, merge feature branches here
feat/phaseN-description  ← working branch per phase
```

Every phase: branch from develop → commit subtasks → `pytest -q` passes → PR to develop → squash merge.

## Environment Variables

See `env.example` for full reference. Critical ones by phase:

```dotenv
# Always needed
DATA_PROVIDER=official_hybrid
FINMIND_TOKEN=          # if using finmind provider

# LLM
GROQ_API_KEY=
LLM_SAFE_MODE=true
OFFICIAL_TLS_INSECURE_FALLBACK=true

# Phase 2+: pCloud
PCLOUD_TOKEN=
PCLOUD_REGION=eu

# Phase 3+: Supabase
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SUPABASE_DB_HOST=       # for Grafana PostgreSQL datasource
SUPABASE_DB_PASSWORD=
```

## Claude Code Agents

Project-level agents live in `.claude/agents/`. Use them for specialized tasks:

| Agent | When to invoke |
|-------|---------------|
| `taiwan-quant-analyst` | Signal design, strategy evaluation, Taiwan market analysis, Chinese investment thesis |
| `fin-pipeline-engineer` | Phase implementation, Docker/Supabase/pCloud, git workflow enforcement |
| `fin-test-engineer` | Writing unit/contract/integration tests, coverage review |
| `fin-architect-doc` | ADR writing, CLAUDE.md updates, documentation consolidation, architecture planning |

## Testing

```bash
pytest -q -m "not integration"   # unit tests only (fast, no external deps)
pytest -q                         # all tests (integration tests skip without credentials)
```

Integration tests in `tests/integration/` are gated with `@pytest.mark.skipif(not os.getenv(...))`.
Legacy smoke test `test/test_decision_system.py` must always pass.
