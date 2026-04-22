# Architecture — fin 台股量化研究工作站

## 1. 現況架構（Phase 5 完成後）

```
┌─────────────────────────────────────────────────────────────┐
│  Entry Points                                               │
│  main.py ──→ src/orchestration/run_daily.py                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────▼──────────────┐
         │  core/ (legacy engine)     │
         │  UniverseBuilder           │
         │  FilterEngine              │  hard rules (price, listing age,
         │  SignalEngine              │  keywords, market type)
         │  DecisionEngine            │
         └──────────┬─────────────────┘
                    │
         ┌──────────▼──────────────────────────────┐
         │  data/                                  │
         │  official_hybrid_client  finmind_client │
         └──────────┬──────────────────────────────┘
                    │
         ┌──────────▼─────────────────┐
         │  llm/                      │
         │  selector.py               │  rule-based OR Groq/OpenAI
         │  explainer.py              │  Chinese investment thesis
         └──────────┬─────────────────┘
                    │
         ┌──────────▼─────────────────────────────────────────┐
         │  src/ pipeline outputs                             │
         │  ArtifactWriter  → workspace/runs/{run_id}/        │
         │  SupabaseClient  → pipeline_runs, candidates …     │
         │  PCloudClient    → /reports/date={d}/run_id={id}/  │
         │  ModelRegistry   → LightGBM champion               │
         │  Predictor       → ML scores                       │
         │  SHAPExplainer   → top-N importances               │
         └──────────┬─────────────────────────────────────────┘
                    │
         ┌──────────▼──────────────────────────────┐
         │  Notifications                          │
         │  DiscordNotifier → webhook + attachments│
         └─────────────────────────────────────────┘

UI / 監控
  src/ui/app.py (Streamlit)   → reads Supabase + workspace artifacts
  Grafana                     → reads Supabase PostgreSQL
  Prometheus                  → service metrics
```

**已知 tech debt（Strangler Fig 期間仍會存在）：**
- `src/orchestration/run_daily.py` ML scoring 傳 `pd.DataFrame()` 空值，SHAP/predict 在 prod 從未真正跑到
- legacy 模組與 `src/` 重疊（`DailyResult` pydantic + artifact parquet + Supabase 三處同樣資料）
- Docker image > 1.5 GB（shap + lightgbm 在 single-stage build）

---

## 2. 目標架構（Phase 11 完成後）

```
┌──────────────────────────────────────────────────────────────────┐
│  Entry Point                                                     │
│  app/orchestration/run_daily.py --profile user_a                 │
└──────────────────────┬───────────────────────────────────────────┘
                       │
         ┌─────────────▼──────────────────────────┐
         │  Qlib Core (qlib_ext/)                 │
         │                                        │
         │  qlib.init(provider_uri, region=TW)    │
         │       ↓                                │
         │  DataHandlerLP (tw_combined.py)        │  features + labels
         │       ↓                                │  from Qlib Expression Engine
         │  LGBModel / qrun workflow YAML         │
         │       ↓                                │
         │  SignalRecord (MLflow recorder)        │
         │       ↓                                │
         │  TwTopkFilteredStrategy                │  TopkDropout + hard rules
         │       ↓                                │
         │  PortAnaRecord / SigAnaRecord          │  IC, Rank IC, Sharpe, MDD
         └──────────────┬─────────────────────────┘
                        │
         ┌──────────────▼────────────────────────────────────────┐
         │  app/ thin layers (post-Qlib post-processors)        │
         │                                                       │
         │  app/control/mlflow_helper.py → get_champion, promote│
         │  app/control/supabase_index.py → qlib_runs table     │
         │  app/llm/ → Chinese thesis (reads SignalRecord)       │
         │  app/notify/discord_notifier.py → IC + Sharpe push   │
         └──────────────┬────────────────────────────────────────┘
                        │
         ┌──────────────▼──────────────────────────────────────┐
         │  Storage                                            │
         │  workspace/mlruns/  (MLflow file store, local)      │
         │  pCloud nightly sync → /mlruns/snapshot={date}/     │
         │  Supabase qlib_runs (mlflow_run_id index only)      │
         └──────────────┬──────────────────────────────────────┘
                        │
         ┌──────────────▼────────────────────┐
         │  app/ui/app.py (Streamlit)        │
         │  mlflow.search_runs() + Supabase  │
         └───────────────────────────────────┘
```

**削減的模組（Phase 11 刪除，共 ~3000 行）：**

| 刪除 | 替換為 |
|------|--------|
| `core/` (7 files) | `qlib_ext/` + Qlib 原生 |
| `src/features/` (3 files) | `qlib_ext/handlers/` (Expression Engine) |
| `src/signals/labeler.py`, `trainer.py`, `predictor.py` | `qlib_ext/workflows/` + MLflow |
| `src/registry/model_registry.py` | `app/control/champion.py` + MLflow tags |
| `src/reporting/converter.py` | Qlib recorder |
| `src/orchestration/run_daily.py` | `app/orchestration/run_daily.py` |
| `main.py`, `sync_data.py`, `sync_financials_slow.py` | `app/orchestration/sync_qlib_data.py` |
| `test/test_decision_system.py` | Qlib integration tests |

**保留的模組：**

| 保留 | 理由 |
|------|------|
| `src/storage/pcloud_client.py` | MLruns backup |
| `src/signals/explainer_shap.py` | post-processor，讀 Qlib SignalRecord |
| `src/monitoring/coverage_checker.py` | 資料品質監控，與框架無關 |
| `src/registry/retrain_gate.py` | 純商業規則 |
| `src/database/` | schema 大幅簡化但保留 |
| `config/` | 全部保留 |
| `notifications/discord_notifier.py` | 搬遷到 `app/notify/`，Phase 10 |
| `llm/` | 介面改為讀 Qlib SignalRecord，Phase 10 |

---

## 3. Strangler Fig 時程

```
Phase 6  [legacy prod] ─────────────────────────────────────────────→
         [qlib_ext/ 骨架 + TW bin data] ┐
Phase 7                                 ├→ [handlers + labels] ┐
Phase 8                                                        ├→ [qrun + MLflow] ┐
Phase 9                                                                           ├→ [backtest + strategy] ┐
Phase 10                                                                                                   ├→ [SHADOW 3d] → [CUTOVER]
Phase 11                                                                                                                          └→ [delete legacy]
```

| Phase | Branch | 主要交付物 | 驗收關鍵指標 |
|-------|--------|-----------|-------------|
| 6 | `feat/phase6-qlib-foundation` | `qlib_ext/` 骨架、TWSE/TPEx/financial bin collectors、nightly sync job | `D.features(["2330.TW"], ["$close", "$volume"], ...)` 回傳非空 DataFrame |
| 7 | `feat/phase7-qlib-handlers` | `tw_alpha.py`、`tw_fundamental.py`、`tw_combined.py`、label expression | handler `fetch()` 數值與 legacy `build_feature_matrix` 差 < 1e-6 |
| 8 | `feat/phase8-qlib-training` | `daily_lgbm.yaml`、MLflow local file store、`qlib_runs` Supabase 表、champion API | `mlflow ui` 看到 run metrics；Supabase `qlib_runs` 有對應 row |
| 9 | `feat/phase9-qlib-backtest` | `TwTopkFilteredStrategy`、TAIEX benchmark、IC / Sharpe / MDD / PNG 報表 | 一次 qrun 產出完整回測報告 PNG + CSV |
| 10 | `feat/phase10-cutover` | `app/orchestration/run_daily.py`、UI/LLM/Discord 重接、3 天 shadow run | Top-20 重疊率 ≥ 70%；shadow 通過後 compose 切換 |
| 11 | `feat/phase11-cleanup` | 刪 legacy、縮 Supabase schema、重寫 CLAUDE.md / README | `pytest -q` 全過；Docker image < 1.5 GB；`grep "from core\."` 回 0 行 |

---

## 4. 資料流（Phase 8+ 後）

```
TWSE/TPEx official API
  ↓
qlib_ext/data_collector/
  twse_collector.py + tpex_collector.py + financial_collector.py
  ↓
workspace/qlib_data/
  calendars/day.txt
  instruments/all.txt
  features/{symbol}/{open,high,low,close,volume,factor,revenue,roe,gm}.day.bin
  ↓
qlib.init(provider_uri="workspace/qlib_data", region=REG_TW)
  ↓
DataHandlerLP (tw_combined.py)
  Expression Engine → tech + fundamental features + 20-day forward return label
  ↓
DatasetH (train / valid / test segments)
  ↓
qrun daily_lgbm.yaml
  LGBModel.fit()
  SignalRecord → workspace/mlruns/{exp_id}/{run_id}/artifacts/
  SigAnaRecord → IC, Rank IC (MLflow metrics)
  PortAnaRecord → Sharpe, MDD, Turnover (MLflow metrics)
  ↓
app/control/mlflow_helper.py
  get_champion(family="lgbm_binary_tw")
  ↓
app/llm/ → Chinese investment thesis
  ↓
app/notify/ → Discord push (IC + Sharpe + top-K candidates)
  ↓
Supabase qlib_runs (index: mlflow_run_id → profile + status + metrics summary)
  ↓
pCloud /mlruns/snapshot={date}/ (nightly backup)
```

---

## 5. 相關決策文件

| ADR | 標題 | 狀態 |
|-----|------|------|
| [ADR-001](decisions/ADR-001-qlib-integration.md) | 全面遷移到 Qlib（Option C — Greenfield） | Accepted |
| ADR-002 | Supabase 降格為 control-plane index only | Planned (Phase 11) |
| ADR-003 | MLflow local file store + pCloud backup（不架 MLflow server） | Planned (Phase 11) |
