# ADR-001: Full Qlib Migration（選項 C — Greenfield Architecture）

**Status:** Implemented
**Date:** 2026-04-22
**Implemented:** 2026-04-27
**Deciders:** Hank, Claude Code
**Supersedes:** 內部初稿（選項 A，同日起草後被推翻）

---

## Context

Phase 5 結束後 fin 具備完整 daily screening pipeline（LightGBM + registry + SHAP），但經盤點有下列結構性問題：

1. **核心介面自寫過多**：`core/decision_engine.py`、`core/signal_engine.py`、`src/features/*`、`src/signals/*`、`src/registry/model_registry.py`、`src/reporting/converter.py` 都是自寫，與社群主流不接軌
2. **抽象疊床架屋**：`DailyResult` pydantic、artifact parquet、Supabase、pCloud 同時存在，職責重疊（一份資料三處表達）
3. **ML 只接了半套**：`run_daily.py` 把空 DataFrame 餵給 predictor（★tech debt），ML scores / SHAP 在生產路徑幾乎沒跑到
4. **回測空白**：無 IC / Rank IC / Turnover / Sharpe / MDD / 分位數績效
5. **維護成本高**：新增指標要動 5–7 個檔，rule 變更容易留下不一致

Microsoft Qlib (https://github.com/microsoft/qlib) 是成熟量化框架：`REG_TW` 已合併進主線、model zoo 含 LGB/LSTM/Transformer/TRA/HIST、原生整合 MLflow、backtest/analysis 一應俱全。使用者選擇 **不追求短期交付、追求最少長期技術債**。

## Decision

**選項 C — 全面遷移到 Qlib**。

核心原則：
1. **Qlib 為核心**：data / features / labels / models / backtest / analysis 全部走 Qlib 標準介面
2. **fin 周邊為 post-processors**：LLM 中文選股論述、Discord、Streamlit UI、Portfolio YAML 都退化為「讀 Qlib recorder」的薄層
3. **Supabase 降格為 control plane index**：只存 `mlflow_run_id` 對應使用者 profile、排程狀態、UI 需要的摘要；不再存放 metrics / artifacts
4. **MLflow 為 model registry 後端**（Qlib 原生），本地 file store + pCloud nightly sync，不架 MLflow server
5. **Strangler Fig 策略**：Phase 6–9 新結構與 legacy 並行，Phase 10 一次 cutover，Phase 11 刪除 legacy

### 目標架構

```
fin/
├── qlib_ext/                    ← 新，TW-specific Qlib 擴充
│   ├── data_collector/          ← TWSE/TPEx → Qlib bin converter
│   │   ├── twse_collector.py
│   │   ├── tpex_collector.py
│   │   └── financial_collector.py   (月營收/季財報)
│   ├── handlers/                ← DataHandlerLP 子類
│   │   ├── tw_alpha.py          (技術面，取代 src/features/tech_features.py)
│   │   └── tw_fundamental.py    (基本面，取代 src/features/fund_features.py)
│   ├── strategies/              ← 含台股 hard rules 的策略
│   │   └── tw_topk_dropout.py   (TopkDropout + keyword exclusion + price floor + listing age)
│   └── workflows/               ← qrun YAML configs
│       ├── daily_lgbm.yaml
│       ├── backtest_only.yaml
│       └── retrain.yaml
│
├── app/                         ← fin 特有層（post-Qlib）
│   ├── control/                 ← Supabase 薄索引
│   ├── notify/                  ← Discord
│   ├── llm/                     ← 中文選股論述（讀 SignalRecord）
│   ├── orchestration/
│   │   ├── run_daily.py         ← qrun + LLM + Discord 編排
│   │   └── run_backtest.py
│   └── ui/                      ← Streamlit（讀 qlib.workflow.R + Supabase）
│
├── config/                      ← 保留 profiles + portfolios
├── docker/
├── compose/
├── scripts/
└── tests/
```

### Cutover 後刪除的 legacy 模組
- `core/`（全部）
- `src/features/`、`src/signals/labeler.py`、`src/signals/trainer.py`、`src/signals/predictor.py`
- `src/registry/model_registry.py`（`retrain_gate.py` 保留）
- `src/reporting/`、`src/storage/artifact_writer.py`
- `src/orchestration/run_daily.py` / `run_signal.py` / `run_report.py`
- `main.py`、`sync_data.py`、`sync_financials_slow.py`
- `test/test_decision_system.py`（legacy smoke）

### 保留（調整即可）
- `src/storage/pcloud_client.py`（MLruns backup）
- `src/signals/explainer_shap.py`（post-processor，讀 Qlib SignalRecord）
- `src/monitoring/coverage_checker.py`（資料品質監控）
- `src/registry/retrain_gate.py`（純商業規則）
- `src/database/`（schema 大幅簡化）
- `config/` 全部
- `notifications/discord_notifier.py`
- `llm/`（selector/explainer，介面改為讀 Qlib SignalRecord）

## Consequences

### 正面
- **框架標準化**：新增指標走 Qlib Expression Engine，不必動 Python；新增 model 照 `qlib.model.base.Model` 介面實作
- **Model zoo 可用**：LightGBM、LSTM、Transformer、TRA、HIST、TabNet、TFT 立即可跑
- **回測/分析一次到位**：IC、Rank IC、ICIR、Turnover、Sharpe、MDD、分位數累積收益
- **技術債大幅降低**：刪 ~15 個自寫模組，預估少 3000 行維護代碼
- **MLflow UI 免費**：MLflow 自帶 experiment tracking UI，與 Streamlit 搭配

### 負面 / 風險
- **工作量 25–40 人日**（含測試、文件、cutover 風險控管）
- **學習曲線**：Qlib Expression Engine、DataHandler、Strategy 都要學
- **TW-specific 邏輯要重寫**：keyword exclusion、listing age、price floor → 改寫成 strategy filter
- **LLM 論述接口要重構**：原本讀 `DailyResult`，改為讀 Qlib `SignalRecord`
- **Streamlit UI 大改**：改為呼叫 `qlib.workflow.R.list_recorders()` 再交叉 Supabase index
- **Cutover 當下有風險**：Phase 10 當天 prod pipeline 換軌，要準備好 rollback（`v0.5-legacy` tag）
- **Supabase schema 破壞性變更**：需要 migration 腳本或乾脆 drop 重建（反正是個人專案）

### 驗收標的（整個遷移完成後）
1. `python -m app.orchestration.run_daily --profile user_a` 跑完整條 qrun pipeline，輸出進 MLflow
2. Streamlit UI 從 MLflow recorder 讀資料顯示
3. Discord 推送包含 Qlib 計算的 IC、Sharpe
4. 刪除所有 legacy 模組後，`pytest -q` 全過
5. Docker image < 1.5 GB（原本 1.5+ GB 因為塞了重複功能）
6. `docs/architecture.md` 更新到新架構，舊 `CLAUDE.md` 同步

## Alternatives Considered

| 選項 | 工作量 | 放棄原因 |
|------|-------|---------|
| A: Backtest-only（Qlib 只當回測工具） | 3–5 人日 | 舊架構保留 → 技術債沒解決 |
| B: qrun 訓練 + backtest，其他保留 | 10–15 人日 | 半遷移 = 最糟：同時學 Qlib 又要維護 legacy，兩套 registry/artifact 並存 |
| **C: 全面遷移** | **25–40 人日** | **採用** — 使用者明確要求「最合適、最沒技術債」 |

## Strangler Fig 策略

```
Time →

Phase 6  [legacy prod] ────────────────────────────────→
         [Qlib data]  ┐
Phase 7              ├→ [Qlib features]    ┐
Phase 8                                    ├→ [Qlib training]  ┐
Phase 9                                                        ├→ [Qlib backtest]  ┐
Phase 10                                                                           ├→ [CUTOVER] ─→ [new prod]
Phase 11                                                                                                   └→ [delete legacy]
```

每個 Phase merge 後 legacy 都還活著；Phase 10 是 cutover day；Phase 11 才真正刪 code。

## Git Tags
- `v0.5-legacy` — Phase 5d merge 之後的 develop HEAD（Phase 6 開工前 tag）
- `v1.0-qlib-cutover` — Phase 10 merge 之後（prod 切換日）
- `v1.1-cleanup` — Phase 11 merge 之後（legacy 刪完）

## Resolution

Phase 11 completed on 2026-04-27. All six acceptance criteria from the Decision section have been met:

1. `python -m app.orchestration.run_daily --profile user_a` runs the full Qlib pipeline end-to-end with MLflow output.
2. Streamlit UI (`app/ui/app.py`) reads directly from MLflow recorders and Supabase index.
3. Discord push (`app/notify/discord_notifier.py`) includes Qlib-computed IC and Sharpe.
4. `pytest -q` passes with 109 unit tests after all legacy modules deleted.
5. Docker image < 1.5 GB (single-stage builds, no duplicate feature/signal code).
6. `docs/architecture.md` and `CLAUDE.md` rewritten to reflect post-Phase-11 state.

**Deleted modules (Phase 11):**
- `core/` (all 7 files — decision_engine, filter_engine, signal_engine, models, universe, strategy_loader, report_renderer)
- `data/` (official_hybrid_client, finmind_client)
- `notifications/` (moved to `app/notify/`)
- `llm/` (moved to `app/llm/`)
- `src/features/` (tech_features, fund_features, feature_builder)
- `src/signals/labeler.py`, `src/signals/trainer.py`, `src/signals/predictor.py`
- `src/registry/model_registry.py`
- `src/reporting/` (schema.py, converter.py)
- `src/storage/artifact_writer.py`
- `src/orchestration/` (run_daily.py, run_signal.py, run_report.py)
- `main.py`, `sync_data.py`, `sync_financials_slow.py`
- `test/test_decision_system.py`

**Git tag:** `v1.1-cleanup`

## References
- Qlib Repo: https://github.com/microsoft/qlib
- Qlib REG_TW: `qlib/config.py` `_default_region_config[REG_TW]`（PR #955/#1310/#1391 已合併）
- Qlib bin dumper: `scripts/dump_bin.py`
- Qlib workflow: `qlib/workflow/__init__.py`（MLflow 封裝）
- Qlib Expression Engine: `qlib/data/ops.py`
- DataHandlerLP 繼承範例: `qlib/contrib/data/handler.py`（Alpha158/Alpha360）
