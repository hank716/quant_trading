# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Personal Taiwan stock screening system. Daily pipeline analyzes TWSE/TPEx markets (~2000 stocks), applies rule-based filters and quantitative signals, and outputs investment candidates with explanations. Infrastructure uses Docker + Supabase + pCloud, with a Streamlit control UI and Grafana dashboards.

**Migration in progress:** Phase 6–11 replace the core pipeline with Microsoft Qlib (Strangler Fig). Legacy code stays alive until Phase 10 cutover. See `docs/decisions/ADR-001-qlib-integration.md` and `docs/architecture.md`.

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

Full overview: `docs/architecture.md`. Quick reference below.

### Current Pipeline (Phase 5 state)

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
  ↓
ModelRegistry            → LightGBM champion model (Supabase + pCloud-backed)
Predictor                → predict_from_champion → score DataFrame
SHAPExplainer            → top-N feature importances → /shap/date={date}/run_id={run_id}/
```

**UI：** 單一 Streamlit 網頁（`http://localhost:8501`）。用戶登入後在此頁面完成所有操作——查看選股、管理持股、調整策略、監控告警，不需碰任何程式碼。Grafana / Prometheus 已移除。

### Module Map

#### Legacy core (will be deleted in Phase 11)

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
| `main.py` | Legacy CLI entry point (compatibility shim) |
| `sync_data.py` | Sync daily TWSE/TPEx market data to local cache |
| `sync_financials_slow.py` | Sync financial statements (quota-aware) |

#### src/ — current active modules (Phase 2–5)

| Path | Responsibility |
|------|---------------|
| `src/orchestration/run_daily.py` | Daily pipeline entry point: artifacts + DB + ML scoring + SHAP |
| `src/database/client.py` | Supabase wrapper with mock fallback |
| `src/database/crud.py` | PipelineRunCRUD, ArtifactCRUD, CandidateCRUD, CoverageCRUD |
| `src/database/schema.sql` | Supabase schema: 11 tables + indexes |
| `src/storage/artifact_writer.py` | Writes parquet/json artifacts to workspace/runs/{run_id}/ |
| `src/storage/pcloud_client.py` | pCloud API wrapper with mock fallback |
| `src/reporting/converter.py` | DailyResult → artifact schemas converter |
| `src/monitoring/coverage_checker.py` | Data quality monitoring (Phase 4) |
| `src/registry/retrain_gate.py` | Retrain trigger logic based on coverage/drift (Phase 4) |
| `src/registry/model_registry.py` | LightGBM model registration + champion tracking (Phase 5c) |
| `src/features/tech_features.py` | Technical features: MA return, volume ratio, institutional flow (Phase 5a) |
| `src/features/fund_features.py` | Fundamental features: revenue momentum, ROE, gross margin (Phase 5a) |
| `src/features/feature_builder.py` | Builds cross-sectional feature matrix (Phase 5a) |
| `src/signals/labeler.py` | Forward return + binary label computation (Phase 5b) |
| `src/signals/trainer.py` | Walk-forward LightGBM training + model save (Phase 5b) |
| `src/signals/predictor.py` | Champion model inference with in-process cache (Phase 5c) |
| `src/signals/explainer_shap.py` | SHAP TreeExplainer + generic fallback, top-N summary (Phase 5d) |
| `src/ui/app.py` | Streamlit UI: Home / Runs / 庫存股 / Coverage / Reports / Run Control / 🤖 模型 |

#### Qlib layer (Phase 6–10, new)

| Path | Responsibility |
|------|---------------|
| `qlib_ext/` | TW-specific Qlib extensions (data collectors, DataHandlers, strategies, workflows) |
| `app/orchestration/` | New pipeline entry points reading from Qlib recorders |
| `app/control/` | Supabase thin index + MLflow helper |
| `app/notify/` | Discord notifier (post-cutover home) |
| `app/ui/` | Streamlit UI (post-cutover, reads MLflow) |

### Directory Structure

```
fin/
├── core/           ← legacy decision engine (alive until Phase 11 deletion)
├── data/           ← legacy data clients
├── llm/            ← selector, explainer, openai_compat
├── notifications/  ← discord notifier (legacy; moves to app/notify/ in Phase 10)
├── config/         ← strategy YAML, profiles, portfolios (kept forever)
├── src/
│   ├── orchestration/   ← run_daily.py (legacy entry point)
│   ├── database/        ← client.py, crud.py, schema.sql
│   ├── storage/         ← pcloud_client.py, artifact_writer.py
│   ├── reporting/       ← schema.py, converter.py
│   ├── signals/         ← labeler, trainer, predictor, explainer_shap
│   ├── features/        ← tech_features, fund_features, feature_builder
│   ├── registry/        ← model_registry (Phase 5c), retrain_gate
│   ├── monitoring/      ← coverage_checker
│   └── ui/              ← app.py (Streamlit)
│
├── qlib_ext/       ← NEW Phase 6+: TW-specific Qlib extensions
│   ├── data_collector/  ← TWSE/TPEx/financial → Qlib bin
│   ├── handlers/        ← DataHandlerLP subclasses
│   ├── strategies/      ← TW TopkDropout + hard rules
│   └── workflows/       ← qrun YAML configs
│
├── app/            ← NEW Phase 6+: post-Qlib thin layers
│   ├── orchestration/   ← run_daily.py (new entry, active from Phase 10)
│   ├── control/         ← Supabase index + MLflow helper
│   ├── notify/          ← Discord (post-cutover)
│   ├── llm/             ← reads Qlib SignalRecord
│   └── ui/              ← Streamlit (post-cutover)
│
├── tests/
│   ├── unit/            ← fast tests, no external deps
│   ├── contract/        ← schema validation
│   └── integration/     ← require Docker or credentials (@pytest.mark.integration)
├── docker/         ← app.Dockerfile, ui.Dockerfile, trainer.Dockerfile, qlib.Dockerfile (Phase 6)
├── compose/        ← docker-compose.yml, prometheus.yml, grafana provisioning
├── scripts/        ← linux/ and windows/ run/start scripts
├── docs/           ← setup guides, ADRs, architecture, work log
├── workspace/      ← runtime data (gitignored): hotdata, runs, outputs, logs, tmp, qlib_data, mlruns
└── main.py         ← legacy entry point (deleted Phase 11)
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
- `shap/{run_id}/shap_summary.json` (when champion model + feature matrix available)

Run state is tracked in Supabase `pipeline_runs` table. Artifacts are uploaded to pCloud at `/reports/date={date}/run_id={run_id}/`.

Post-Phase 8: MLflow stores model artifacts at `workspace/mlruns/` with pCloud nightly backup.

## Qlib Migration (Phase 6–11)

**Decision:** Full migration to Microsoft Qlib (Option C — Strangler Fig).  
**ADR:** `docs/decisions/ADR-001-qlib-integration.md`  
**Architecture:** `docs/architecture.md`

| Phase | Adds | Legacy status |
|-------|------|---------------|
| 6 | `qlib_ext/` + TW bin data layer | Alive, prod |
| 7 | `qlib_ext/handlers/` (features + labels) | Alive, prod |
| 8 | `qlib_ext/workflows/` + MLflow registry | Alive, prod |
| 9 | `qlib_ext/strategies/` + backtest | Alive, prod |
| 10 | `app/orchestration/run_daily.py` — 3-day shadow, then cutover | Alive, standby |
| 11 | Delete `core/`, `src/features/`, `src/signals/trainer`, etc. | Deleted |

**Rollback tags:**
- `v0.5-legacy` — snapshot before Phase 6 starts
- `v1.0-qlib-cutover` — Phase 10 cutover commit
- `v1.1-cleanup` — Phase 11 complete

## Git Workflow

```
main     ← protected, never push directly, only manual review merges here
develop  ← integration branch, merge feature branches here
feat/phaseN-description  ← working branch per phase
docs/description         ← documentation-only branches
```

Every phase: branch from develop → commit subtasks → `pytest -q` passes → PR to develop → squash merge → delete remote branch.

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

# Phase 8+: MLflow
MLFLOW_TRACKING_URI=file:workspace/mlruns
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
Legacy smoke test `test/test_decision_system.py` must always pass until Phase 11 deletion.
