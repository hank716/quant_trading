# Architecture — fin 台股量化研究工作站

**Status: Phase 11 complete. All legacy code deleted. System is fully Qlib-based.**

---

## 1. System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  Entry Point                                                         │
│  python -m app.orchestration.run_daily --profile user_a             │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
         ┌─────────────────────▼──────────────────────────┐
         │  Data Sync  (app/orchestration/sync_qlib_data)  │
         │  qlib_ext/data_collector/                       │
         │    twse_collector + tpex_collector              │
         │    financial_collector                          │
         │        → workspace/qlib_data/ (Qlib bin)       │
         └─────────────────────┬──────────────────────────┘
                               │
         ┌─────────────────────▼──────────────────────────┐
         │  Qlib Core  (qlib_ext/)                        │
         │                                                │
         │  qlib.init(provider_uri, region=REG_TW)        │
         │    ↓                                           │
         │  DataHandlerLP                                 │
         │    tw_alpha.py    — technical features         │
         │    tw_fundamental.py — revenue, ROE, margin    │
         │    ↓                                           │
         │  qrun daily_lgbm.yaml                          │
         │    LGBModel.fit() → pred.pkl                   │
         │    SigAnaRecord  → IC, Rank IC (MLflow)        │
         │    PortAnaRecord → Sharpe, MDD (MLflow)        │
         │    ↓                                           │
         │  TwTopkFilteredStrategy                        │
         │    TopkDropout + keyword exclusion             │
         │    + price floor + listing age                 │
         └─────────────────────┬──────────────────────────┘
                               │
         ┌─────────────────────▼──────────────────────────┐
         │  Post-Processors  (app/)                       │
         │                                                │
         │  app/llm/adapters.py                           │
         │    run_selection()  → QlibRuleBasedSelector    │
         │                    OR QlibLLMSelector          │
         │    run_explanation() → Chinese thesis          │
         │                                                │
         │  app/notify/discord_notifier.py                │
         │    QlibDiscordNotifier.send()                  │
         │    message: IC + Sharpe + top-K candidates     │
         │                                                │
         │  src/database/qlib_crud.py                     │
         │    QlibRunCRUD.update_status()                 │
         │    → Supabase qlib_runs (run_id index)         │
         └─────────────────────┬──────────────────────────┘
                               │
         ┌─────────────────────▼──────────────────────────┐
         │  Storage                                       │
         │  workspace/mlruns/  (MLflow local file store)  │
         │  workspace/runs/    (shap_summary.json)        │
         │  pCloud nightly sync → /mlruns/snapshot={d}/  │
         └─────────────────────────────────────────────────┘

UI
  app/ui/app.py (Streamlit, port 8501)
    streamlit-authenticator → profile mapping
    今日報告 — reads MLflow recorder pred.pkl
    我的持股 — reads/writes config/portfolio_{profile}.yaml
    策略設定 — reads/writes config/strategy_1m.yaml + profiles/{p}.yaml
    模型狀態 — reads MLflow metrics + workspace/runs/shap_summary.json
    回測分析 — reads MLflow runs, renders PNG artifacts
    監控 & 告警 — CoverageChecker + Supabase pipeline_runs + Discord test
```

---

## 2. Data Flow (detail)

```
TWSE/TPEx official API
  ↓
qlib_ext/data_collector/
  twse_collector.py     → OHLCV, institutional flows
  tpex_collector.py     → OHLCV for OTC market
  financial_collector.py → monthly revenue, quarterly ROE, gross margin
  ↓
workspace/qlib_data/
  calendars/day.txt
  instruments/all.txt
  features/{symbol}/*.day.bin
  ↓
qlib.init(provider_uri="workspace/qlib_data", region=REG_TW)
  ↓
DataHandlerLP (tw_alpha + tw_fundamental)
  Expression Engine → tech + fundamental feature matrix
  20-day forward return label
  ↓
DatasetH  (train / valid / test date segments)
  ↓
qrun daily_lgbm.yaml
  LGBModel.fit() → pred.pkl in MLflow recorder
  SigAnaRecord  → IC, Rank IC logged to MLflow
  PortAnaRecord → Sharpe, MDD, Turnover logged to MLflow
  ↓
app/orchestration/run_daily.py
  _load_signal()   → reads pred.pkl, slices latest date
  run_selection()  → top-K candidates (rule_based or LLM)
  run_explanation() → Chinese investment thesis
  ↓
app/notify/discord_notifier.py → webhook push
src/database/qlib_crud.py      → Supabase index update
src/storage/pcloud_client.py   → nightly mlruns backup
```

---

## 3. Module Boundaries

### What Qlib owns

| Concern | Qlib component |
|---------|---------------|
| Feature engineering | DataHandlerLP Expression Engine (`qlib_ext/handlers/`) |
| Label computation | 20-day forward return expression in handler |
| Model training | LGBModel via `qrun` YAML |
| Model artifacts | MLflow recorder (`workspace/mlruns/`) |
| Performance metrics | SigAnaRecord (IC, Rank IC), PortAnaRecord (Sharpe, MDD) |
| Stock selection strategy | TwTopkFilteredStrategy + TopkDropout |
| Backtest | PortAnaRecord + benchmark comparison |

### What app/ owns

| Concern | Module |
|---------|--------|
| Pipeline orchestration | `app/orchestration/run_daily.py` |
| LLM selection + Chinese thesis | `app/llm/selector.py`, `app/llm/explainer.py`, `app/llm/adapters.py` |
| Discord notification | `app/notify/discord_notifier.py` |
| Champion model management | `app/control/champion.py` |
| Portfolio YAML editing | `app/control/portfolio_editor.py` |
| Streamlit UI | `app/ui/app.py` |

### What src/ retains

| Concern | Module |
|---------|--------|
| Supabase client + CRUD | `src/database/client.py`, `src/database/crud.py`, `src/database/qlib_crud.py` |
| pCloud backup | `src/storage/pcloud_client.py` |
| SHAP post-processing | `src/signals/explainer_shap.py` |
| Retrain gate logic | `src/registry/retrain_gate.py` |
| Data coverage monitoring | `src/monitoring/coverage_checker.py` |

---

## 4. Docker Services

```
compose/docker-compose.yml
  ├── quant-ui        (always-on, port 8501)
  │     docker/ui.Dockerfile
  │     streamlit run app/ui/app.py
  │
  ├── quant-daily     (profile: jobs — run by cron or manually)
  │     docker/app.Dockerfile
  │     python -m app.orchestration.run_daily --profile user_a
  │
  ├── quant-trainer   (profile: jobs)
  │     docker/trainer.Dockerfile
  │     python -m app.orchestration.run_training --workflow ...
  │
  ├── qlib-sync       (profile: jobs)
  │     docker/qlib.Dockerfile
  │     python -m app.orchestration.sync_qlib_data --lookback-days 5
  │
  └── quant-sync      (profile: jobs, legacy stub)
        docker/app.Dockerfile
```

One-off job: `docker compose --profile jobs run --rm quant-daily`

---

## 5. Supabase Schema (post-Phase 11)

Four tables only. MLflow is the source of truth for metrics and artifacts; Supabase is a control-plane index.

| Table | Key columns | Purpose |
|-------|-------------|---------|
| `qlib_runs` | `mlflow_run_id`, `profile`, `status`, `metrics` (JSONB), `trade_date` | Run index; UI reads this to list recent runs |
| `backtest_runs` | `mlflow_run_id`, `period_start`, `period_end`, `metrics` (JSONB) | Backtest result index |
| `coverage_snapshots` | `checked_at`, `coverage` (JSONB), `alerts` | Data quality time series |
| `system_alerts` | `alert_type`, `severity`, `message`, `created_at` | Retrain gate + coverage alerts |

Schema DDL: `src/database/schema.sql`

---

## 6. Configuration Hierarchy

```
config/strategy_1m.yaml          ← hard rules, Qlib strategy params, selection limits
config/profiles/{profile}.yaml   ← LLM provider, Discord webhook, portfolio path
config/portfolio_{profile}.yaml  ← current holdings (edited via Streamlit 我的持股)
config/auth_users.yaml           ← streamlit-authenticator credentials (gitignored)
.env.local                       ← secrets: API keys, webhook URLs (gitignored)
```

Strategy YAML controls `TwTopkFilteredStrategy` params (min_price, min_listing_days, keyword exclusions, max_consider, max_watch). Changes take effect on the next `run_daily` invocation.

---

## 7. Decision Log

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](decisions/ADR-001-qlib-integration.md) | Full Qlib migration (Option C — Strangler Fig) | Implemented |

---

## 8. Rollback Tags

| Tag | Meaning |
|-----|---------|
| `v0.5-legacy` | Phase 5 snapshot — fully functional legacy pipeline, pre-Qlib |
| `v1.0-qlib-cutover` | Phase 10 cutover — Qlib active, legacy on standby |
| `v1.1-cleanup` | Phase 11 complete — legacy deleted, current production state |
