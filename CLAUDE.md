# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Personal Taiwan stock screening system. Daily pipeline analyzes TWSE/TPEx markets (~2000 stocks) using Microsoft Qlib as the core ML framework, applies rule-based hard filters and LightGBM signals, and outputs investment candidates with Chinese-language explanations. Infrastructure uses Docker + Supabase (control plane) + pCloud (artifact backup) + MLflow (model registry), with a Streamlit UI.

**Phase 11 complete.** All legacy code has been deleted. The active system is fully Qlib-based. See `docs/decisions/ADR-001-qlib-integration.md` and `docs/architecture.md`.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests (unit only, no external deps)
pytest -q -m "not integration"

# Run all tests including integration
pytest -q

# Daily pipeline (sync + train + signal + Discord + Supabase)
python -m app.orchestration.run_daily --profile user_a

# Skip data sync (use cached Qlib bin data)
python -m app.orchestration.run_daily --profile user_a --skip-sync

# Skip training (use existing MLflow recorder for signal)
python -m app.orchestration.run_daily --profile user_a --skip-train

# Sync Qlib bin data from TWSE/TPEx
python -m app.orchestration.sync_qlib_data --lookback-days 5

# Run training workflow only
python -m app.orchestration.run_training --workflow qlib_ext/workflows/daily_lgbm.yaml

# Run backtest only
python -m app.orchestration.run_backtest

# Apply Supabase schema (requires DATABASE_URL)
bash scripts/linux/apply_schema.sh

# Start Streamlit UI
streamlit run app/ui/app.py
```

**Key `run_daily` flags:**
- `--profile {user_a|user_b|default}` — selects user config, portfolio, and Discord webhook
- `--skip-sync` — skip Qlib data sync step
- `--skip-train` — skip qrun training, load signal from latest MLflow recorder
- `--workflow PATH` — override Qlib workflow YAML (default: `qlib_ext/workflows/daily_lgbm.yaml`)
- `--top-k N` — hint for top-K selection (effective value comes from `strategy_cfg`)

## Architecture

Full diagram: `docs/architecture.md`. Quick reference below.

### Pipeline (post-Phase 11)

```
sync_qlib_data           → TWSE/TPEx → Qlib bin (workspace/qlib_data/)
  ↓
run_training             → qrun daily_lgbm.yaml → LightGBM → MLflow recorder
  ↓
_load_signal             → reads pred.pkl from MLflow recorder (latest date slice)
  ↓
app/llm/adapters         → run_selection (QlibRuleBasedSelector / QlibLLMSelector)
                         → run_explanation (QlibRuleBasedExplainer / QlibLLMExplainer)
  ↓
QlibDiscordNotifier      → webhook with IC / Sharpe / candidate thesis
  ↓
QlibRunCRUD              → Supabase qlib_runs: mlflow_run_id, status, metrics
  ↓
PCloudClient             → nightly backup of workspace/mlruns/
```

**UI:** Single Streamlit page (`http://localhost:8501`). Auth via `streamlit-authenticator` (config: `config/auth_users.yaml`). Six pages: 今日報告 / 我的持股 / 策略設定 / 模型狀態 / 回測分析 / 監控 & 告警. All data sourced from MLflow recorders + Supabase index.

### Module Map

#### app/ — post-Qlib thin layers (active)

| Path | Responsibility |
|------|---------------|
| `app/orchestration/run_daily.py` | Daily pipeline entry point: sync → train → signal → LLM → Discord → Supabase |
| `app/orchestration/run_training.py` | Runs `qrun` workflow YAML; returns exit code |
| `app/orchestration/sync_qlib_data.py` | Triggers `qlib_ext/data_collector/` to sync Qlib bin data |
| `app/orchestration/run_backtest.py` | Standalone backtest via Qlib workflow |
| `app/control/portfolio_editor.py` | load/save/add/remove portfolio holdings (YAML-backed) |
| `app/control/champion.py` | Champion model get/list/promote logic (MLflow-backed) |
| `app/control/mlflow_helper.py` | `get_run_metrics()` — thin MLflow client wrapper |
| `app/llm/selector.py` | QlibRuleBasedSelector / QlibLLMSelector (reads MLflow SignalRecord) |
| `app/llm/explainer.py` | QlibRuleBasedExplainer / QlibLLMExplainer (Chinese thesis) |
| `app/llm/adapters.py` | `run_selection()` / `run_explanation()` — dispatcher with safe-mode logic |
| `app/notify/discord_notifier.py` | QlibDiscordNotifier + `build_message()` |
| `app/ui/app.py` | Streamlit UI (6 pages, streamlit-authenticator, reads MLflow + Supabase) |

#### qlib_ext/ — TW-specific Qlib extensions (active)

| Path | Responsibility |
|------|---------------|
| `qlib_ext/__init__.py` | `init_tw_qlib()` — initialize Qlib with TW region + workspace path |
| `qlib_ext/data_collector/twse_collector.py` | TWSE daily price/volume → Qlib bin |
| `qlib_ext/data_collector/tpex_collector.py` | TPEx daily price/volume → Qlib bin |
| `qlib_ext/data_collector/financial_collector.py` | Monthly revenue + quarterly financials → Qlib bin |
| `qlib_ext/handlers/tw_alpha.py` | DataHandlerLP: technical features (MA, volume ratio, inst. flow) |
| `qlib_ext/handlers/tw_fundamental.py` | DataHandlerLP: fundamental features (revenue momentum, ROE, gross margin) |
| `qlib_ext/strategies/tw_topk_dropout.py` | TopkDropout + TW hard rules (keyword exclusion, price floor, listing age) |
| `qlib_ext/workflows/daily_lgbm.yaml` | Main qrun config: LightGBM training + prediction |
| `qlib_ext/workflows/backtest_only.yaml` | Backtest-only qrun config |
| `qlib_ext/workflows/retrain.yaml` | Scheduled retrain config |

#### src/ — infrastructure utilities (active, kept)

| Path | Responsibility |
|------|---------------|
| `src/database/client.py` | Supabase wrapper with mock fallback |
| `src/database/crud.py` | PipelineRunCRUD, CandidateCRUD, CoverageCRUD |
| `src/database/qlib_crud.py` | QlibRunCRUD — `qlib_runs` table operations |
| `src/database/schema.sql` | Supabase schema: `qlib_runs`, `backtest_runs`, `coverage_snapshots`, `system_alerts` |
| `src/storage/pcloud_client.py` | pCloud API wrapper with mock fallback |
| `src/signals/explainer_shap.py` | SHAP TreeExplainer + top-N summary (post-processor, reads Qlib SignalRecord) |
| `src/signals/schema.py` | Pydantic schemas for signal output |
| `src/registry/retrain_gate.py` | Retrain trigger logic based on coverage / drift |
| `src/monitoring/coverage_checker.py` | Data quality monitoring |
| `src/ui/app.py` | Legacy Streamlit UI (reference only — superseded by `app/ui/app.py`) |

### Directory Structure

```
fin/
├── app/
│   ├── orchestration/   ← run_daily.py, run_training.py, sync_qlib_data.py, run_backtest.py
│   ├── control/         ← portfolio_editor.py, champion.py, mlflow_helper.py
│   ├── llm/             ← selector.py, explainer.py, adapters.py
│   ├── notify/          ← discord_notifier.py
│   └── ui/              ← app.py (Streamlit, active)
│
├── qlib_ext/
│   ├── data_collector/  ← twse_collector.py, tpex_collector.py, financial_collector.py
│   ├── handlers/        ← tw_alpha.py, tw_fundamental.py
│   ├── strategies/      ← tw_topk_dropout.py
│   └── workflows/       ← daily_lgbm.yaml, backtest_only.yaml, retrain.yaml
│
├── src/
│   ├── database/        ← client.py, crud.py, qlib_crud.py, schema.sql
│   ├── storage/         ← pcloud_client.py
│   ├── signals/         ← explainer_shap.py, schema.py
│   ├── registry/        ← retrain_gate.py
│   ├── monitoring/      ← coverage_checker.py
│   └── ui/              ← app.py (legacy reference, not active)
│
├── config/
│   ├── profiles/        ← {profile}.yaml: strategy, portfolio, LLM provider, Discord
│   ├── strategy_1m.yaml ← hard rules, signal thresholds, selection limits
│   ├── portfolio_{profile}.yaml  ← current holdings (editable via UI)
│   ├── auth_users.yaml  ← streamlit-authenticator config (gitignored)
│   └── auth_users.yaml.example
│
├── tests/
│   ├── unit/            ← fast tests, no external deps (109 tests)
│   ├── contract/        ← schema validation
│   └── integration/     ← require Docker or credentials (@pytest.mark.integration)
│
├── docker/
│   ├── app.Dockerfile   ← general app image
│   ├── ui.Dockerfile    ← Streamlit UI image
│   ├── trainer.Dockerfile
│   └── qlib.Dockerfile  ← Qlib data sync image
│
├── compose/
│   └── docker-compose.yml  ← services: quant-ui, quant-daily, quant-trainer, qlib-sync, quant-sync
│
├── scripts/             ← linux/ and windows/ run/start scripts
├── docs/                ← setup guides, ADRs, architecture, work log
└── workspace/           ← runtime data (gitignored)
    ├── qlib_data/       ← Qlib bin data synced from TWSE/TPEx
    ├── mlruns/          ← MLflow experiment tracking store
    ├── hotdata/         ← cached lookups
    ├── runs/            ← per-run SHAP output (shap_summary.json)
    └── logs/
```

### Configuration Hierarchy

```
config/strategy_1m.yaml          ← hard rules, signal thresholds, selection limits
config/profiles/{profile}.yaml   ← LLM provider, Discord webhook, portfolio path
config/portfolio_{profile}.yaml  ← current holdings (shown in Streamlit UI, editable)
config/auth_users.yaml           ← streamlit-authenticator credentials (gitignored)
.env.local                       ← secrets: API tokens, webhook URLs, LLM keys (gitignored)
```

### Docker Services

| Service | Dockerfile | Command |
|---------|------------|---------|
| `quant-ui` | `docker/ui.Dockerfile` | `streamlit run app/ui/app.py` (port 8501, always-on) |
| `quant-daily` | `docker/app.Dockerfile` | `python -m app.orchestration.run_daily --profile user_a` (profile: jobs) |
| `quant-trainer` | `docker/trainer.Dockerfile` | `python -m app.orchestration.run_training --workflow ...` (profile: jobs) |
| `qlib-sync` | `docker/qlib.Dockerfile` | `python -m app.orchestration.sync_qlib_data --lookback-days 5` (profile: jobs) |
| `quant-sync` | `docker/app.Dockerfile` | legacy sync stub (profile: jobs) |

Run one-off jobs: `docker compose --profile jobs run --rm quant-daily`

### LLM Safe Mode

When `LLM_SAFE_MODE=true` (default) and selector and explainer use the same external LLM, the explainer auto-demotes to `rule_based` to halve API calls. Configured in `app/llm/adapters.py`.

LLM responses are cached to `.cache/llm/` by SHA256 of the request payload.

### Data Flow

Qlib bin data lives at `workspace/qlib_data/`. `qlib_ext.init_tw_qlib()` initializes Qlib with this path on every process start. MLflow tracking URI defaults to `file:workspace/mlruns`; set `MLFLOW_TRACKING_URI` to override. pCloud backup uploads `workspace/mlruns/` nightly.

### Supabase Tables (post-Phase 11)

| Table | Purpose |
|-------|---------|
| `qlib_runs` | MLflow run index: `mlflow_run_id`, `profile`, `status`, `metrics` JSON, timestamps |
| `backtest_runs` | Backtest results index |
| `coverage_snapshots` | Data quality snapshots from `coverage_checker` |
| `system_alerts` | Retrain gate alerts and coverage warnings |

## Git Workflow

```
main     ← protected, never push directly, only manual review merges here
develop  ← integration branch, merge feature branches here
feat/description   ← working branches
docs/description   ← documentation-only branches
```

Every change: branch from develop → commit → `pytest -q` passes → PR to develop → squash merge → delete remote branch.

**Tags:**
- `v0.5-legacy` — Phase 5 snapshot (pre-Qlib migration)
- `v1.0-qlib-cutover` — Phase 10 cutover
- `v1.1-cleanup` — Phase 11 complete (current)

## Environment Variables

See `env.example` for full reference. Required variables:

```dotenv
# Qlib data
MLFLOW_TRACKING_URI=file:workspace/mlruns

# LLM (at least one required if not using rule_based)
GROQ_API_KEY=
LLM_SAFE_MODE=true

# pCloud (artifact backup)
PCLOUD_TOKEN=
PCLOUD_REGION=eu

# Supabase (control plane)
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SUPABASE_DB_HOST=
SUPABASE_DB_PASSWORD=

# TLS (TWSE endpoints sometimes have cert issues)
OFFICIAL_TLS_INSECURE_FALLBACK=true
```

## Claude Code Agents

Project-level agents live in `.claude/agents/`. Use them for specialized tasks:

| Agent | When to invoke |
|-------|---------------|
| `taiwan-quant-analyst` | Signal design, strategy evaluation, Taiwan market analysis, Chinese investment thesis |
| `fin-pipeline-engineer` | Pipeline implementation, Docker/Supabase/pCloud, git workflow enforcement |
| `fin-test-engineer` | Writing unit/contract/integration tests, coverage review |
| `fin-architect-doc` | ADR writing, CLAUDE.md updates, documentation consolidation, architecture planning |

## Testing

```bash
pytest -q -m "not integration"   # 109 unit tests (fast, no external deps)
pytest -q                         # all tests (integration tests skip without credentials)
```

Integration tests in `tests/integration/` are gated with `@pytest.mark.skipif(not os.getenv(...))`.
