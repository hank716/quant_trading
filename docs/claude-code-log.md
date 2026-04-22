# Claude Code 工作紀錄

每次啟動請在此檔最上方新增一筆：

## 2026-04-22 (Phase 8 — Qlib Training + MLflow Registry)
- 啟動時所在 branch：feat/phase7-qlib-handlers（Phase 7 PR 已 open，先補 TASKS.md 標記 [x] 再 merge）
- 使用 agents：fin-pipeline-engineer（Phase 8 全部實作）
- 完成的子任務：
  - Phase 7 收尾：TASKS.md 補 [x]、PR #13 squash merge → develop
  - Phase 8 全部（8.1–8.8）：
  - `qlib_ext/workflows/daily_lgbm.yaml`：正式訓練 workflow（2020–2024，LGBModel TW 參數）
  - `qlib_ext/workflows/retrain.yaml`：全量 retrain（2020–2025）
  - `qlib_ext/workflows/quick_debug.yaml`：快速開發用（2022–2023，num_threads:4）
  - `app/control/mlflow_helper.py`：list_experiments / get_run_metrics / get_recorder
  - `qlib_ext/__init__.py`：init_tw_qlib 加入 MLFLOW_TRACKING_URI setdefault
  - `env.example`：新增 MLFLOW_TRACKING_URI
  - `app/orchestration/run_training.py`：--workflow 參數，呼叫 qrun subprocess，寫 Supabase qlib_runs
  - `src/database/schema.sql`：qlib_runs 表 + 3 indexes
  - `src/database/qlib_crud.py`：QlibRunCRUD（register / update_status / get_by_run_id / list_by_family）
  - `app/control/champion.py`：get_champion / promote / list_candidates（MLflow tag-based）
  - `compose/docker-compose.yml`：quant-trainer command → app.orchestration.run_training
  - `tests/unit/test_mlflow_helper.py`（4 tests）+ `tests/unit/test_qlib_crud.py`（7 tests）
  - `tests/integration/test_qrun_smoke.py`（skipif no workspace/qlib_data）
  - 199 passed, 6 deselected
- 遇到的卡點：端到端 qrun 驗收（8.8）需要真實 workspace/qlib_data；待 qlib-sync job 跑完後手動驗證
- 下次繼續：Phase 9（Backtest + Strategy，feat/phase9-qlib-backtest）

## 2026-04-22 (Phase 7 — TW DataHandlers)
- 啟動時所在 branch：feat/phase7-qlib-handlers（從 develop 開出）
- 使用 agents：直接實作（無子 agent）
- 完成的子任務：Phase 7 全部（7.1–7.8）
  - fix(phase6)：先修 `dump_to_bin()` — DumpDataAll 在 pyqlib 0.9.8+ 已移除，改用直接 numpy float32 binary write；新增 2 個 bin 格式驗證測試（共 10 tests）
  - requirements.txt：`pyqlib @ git+https://github.com/microsoft/qlib.git`（改用 GitHub URL）
  - `qlib_ext/handlers/tw_alpha.py`：TWAlphaHandler（TECH_MAn_RET / TECH_VOLn_RATIO / TECH_RETnD / TECH_STDnD / TECH_HL_RANGE，共 14 技術特徵）
  - `qlib_ext/handlers/tw_fundamental.py`：TWFundamentalHandler（FUND_REV_YOY/MOM/POS_RATIO + FUND_ROE/ROE_YOY + FUND_GM/GM_YOY，共 7 基本面特徵）
  - `qlib_ext/handlers/tw_combined.py`：TWCombinedHandler（合併 tech + fundamental + label；`include_fundamental=False` 可降級）
  - Label 定義：`LABEL_RET20D`（Ref($close,-20)/$close-1）+ `LABEL_BIN20D`（Gt(..., 0)）
  - `qlib_ext/workflows/handler_config.yaml`：可餵 qrun 的 handler YAML 片段（含 tech-only 與 combined 兩種設定）
  - `qlib_ext/handlers/__init__.py`：export 三個 handler class
  - `tests/unit/test_handler_equivalence.py`：16 cases（feature count、名稱前綴、label 一致性、no duplicate）
  - `src/signals/explainer_shap.py`：新增 `prepare_feature_matrix_from_handler()`（MultiIndex → 2D，按 TECH_/FUND_ 前綴過濾）
  - 188 passed, 5 deselected
- 遇到的卡點：DumpDataAll 不存在（已在 Phase 6 fix commit 解決）；DataHandlerLP 需要 `data_loader` dict config，不能直接傳 fields list
- 下次繼續：Phase 8（Qlib Training + MLflow，feat/phase8-qlib-training）

## 2026-04-22 (Phase 6 — Qlib Foundation)
- 啟動時所在 branch：feat/phase6-qlib-foundation（從 develop 開出）
- 使用 agents：fin-pipeline-engineer（全部實作）
- 完成的子任務：Phase 6 全部（6.1–6.10）
  - requirements.txt：pyqlib>=0.9.5
  - docker/qlib.Dockerfile：multi-stage build（gcc/g++/cython3 → slim runtime）
  - qlib_ext/ 骨架 + app/ 骨架（orchestration/control/notify/llm/ui）
  - qlib_ext/data_collector/twse_collector.py：TWSECollector（CSV staging → DumpDataAll）
  - qlib_ext/data_collector/tpex_collector.py：TPExCollector（subclass）
  - qlib_ext/data_collector/merge_universe.py：instruments/all.txt
  - qlib_ext/data_collector/financial_collector.py：月營收 + 季財報 → daily ffill
  - app/orchestration/sync_qlib_data.py：CLI（--lookback-days）
  - compose/docker-compose.yml：新增 qlib-sync service（profiles: jobs）
  - scripts/linux/run_qlib_sync.sh
  - app/orchestration/backup_qlib_data.py：zip → pCloud
  - tests/unit/test_twse_collector.py：7 cases（importorskip qlib）
  - tests/integration/test_qlib_init.py
  - docs/qlib-data-format.md + docs/qlib-setup.md
  - 162 passed, 1 skipped
- 遇到的卡點：pyqlib 未安裝時 unit test 用 importorskip 跳過
- 下次繼續：Phase 7（feat/phase7-qlib-handlers，需先跑 sync_qlib_data 建立 bin）

## 2026-04-22 (Pre-Qlib 文件整理)
- 啟動時所在 branch：develop（PR #10 docs/adr-001-qlib-migration 尚未合併）
- 任務：在 Phase 6 開工前同步文件、整理目錄結構說明
- 產出：
  - `README.md`：修正 Phase 4/5 狀態（標為 ✅），新增 Phase 6–11 行，補 ADR / architecture 文件連結
  - `CLAUDE.md`：補 Phase 4/5 模組表（coverage_checker, retrain_gate, labeler, trainer, predictor, explainer_shap）；新增「Qlib Migration」一節（Strangler Fig 表格 + rollback tags）；目錄結構標記 legacy vs new
  - `docs/architecture.md`：新建；含現況架構圖、目標架構圖、Strangler Fig 時程表、資料流、相關 ADR 索引
  - `TASKS.md`：Phase 6–11 各加入「前置條件」與具體「完成定義」checklist；底部結構圖改為 Strangler Fig 版本（標 legacy / keep / new）
- 未做（留 Slice C）：run_daily.py ML scoring 修正、trainer __main__ 補寫
- 下次繼續：merge PR #10 + PR（此次）→ 建立 v0.5-legacy tag → 開 feat/phase6-qlib-foundation

## 2026-04-22 (Qlib 全面遷移 — Option C 改版)
- 啟動時所在 branch：develop（Phase 5d merge 後）
- 使用者決策：推翻 Option A（backtest-only），改採 **Option C 全面遷移到 Qlib**，理由「最合適、最沒技術債」
- 產出：
  - `docs/decisions/ADR-001-qlib-integration.md`：重寫為 Option C（Greenfield），含目標架構（`qlib_ext/` + `app/`）、Strangler Fig 時程、刪除/保留模組清單、git tags（`v0.5-legacy` / `v1.0-qlib-cutover` / `v1.1-cleanup`）
  - `TASKS.md` 重整 Phase 6–11：
    - Phase 6 Qlib 基礎建設 + TW 資料層（10 tasks）
    - Phase 7 TW Features/Labels DataHandler（8 tasks）
    - Phase 8 Qlib Training + MLflow Registry（8 tasks）
    - Phase 9 Backtest + Strategy + Analysis（7 tasks）
    - Phase 10 Orchestration Cutover（10 tasks，★ cutover day）
    - Phase 11 Legacy 清理 + 文件重寫（7 tasks）
- 關鍵決策：
  - MLflow 取代 `src/registry/model_registry.py`（Qlib 原生），local file store + pCloud nightly sync，不架 MLflow server
  - Supabase 降格為 control plane index（只存 `mlflow_run_id` → profile/排程狀態）
  - TW hard rules（keyword exclusion / listing age / price floor）改寫到 `qlib_ext/strategies/tw_topk_dropout.py`
  - Phase 10 shadow run 3 天再切換，`v0.5-legacy` tag 保留 rollback 能力
- 下次繼續：Phase 6.1（requirements.txt 加 pyqlib>=0.9.6 + qlib_ext/ 骨架，feat/phase6-qlib-foundation）

## 2026-04-22 (Qlib 初評 — Option A，已推翻)
- 產出：ADR-001 v1（Option A backtest-only，3–5 人日），TASKS.md 新增 Phase 6/7/8（backtest adapter / Alpha158 horse-race / 技術債）
- 推翻原因：使用者要求「最合適、最沒技術債」，Option A 保留舊架構 → 改走 Option C
- 技術債盤點（已併入 Phase 10/11）：
  - `run_daily.py:162` ML scoring 傳空 DataFrame → SHAP 與 predict 永遠跑不到（★優先）
  - `run_daily.py:87` coverage 用 regex 解析 notes，脆弱
  - `quant-trainer` service 沒有 orchestration，`python -m src.signals.trainer` 缺 `__main__`
  - Docker image 超過 1.5 GB，shap + lightgbm 該拆 multi-stage

## 2026-04-22 (Phase 5d)
- 啟動時所在 branch：develop → feat/phase5d-shap
- 完成的子任務：Phase 5d 全部（5d.1–5d.7）+ Phase 5.x 部分驗收
  - requirements.txt：shap>=0.43.0
  - src/signals/explainer_shap.py：compute_shap_summary（TreeExplainer + generic fallback）、write_shap_summary
  - src/orchestration/run_daily.py：SHAP hook（champion + non-empty feature matrix 才觸發）+ pCloud upload
  - src/ui/app.py：新增「🤖 模型」頁（champion metrics、per-user 訓練參數、候選列表、Promote 按鈕、SHAP bar chart）；補 import os
  - tests/unit/test_explainer_shap.py：10 cases（mock shap module）
  - 162 tests pass
- 遇到的卡點：test fallback mock 鏈設置錯誤（`gen_exp_result(X).values` 未正確接線），修正 mock 結構解決
- 下次繼續：完整 end-to-end 流程驗證（train → register → predict → SHAP），需真實資料

## 2026-04-22 (Phase 5c)
- 啟動時所在 branch：develop → feat/phase5c-model-registry
- 完成的子任務：Phase 5c 全部（5c.1–5c.5）
  - src/registry/model_registry.py：register / get_champion / list_candidates / promote / download_model
  - src/signals/predictor.py：predict + predict_from_champion（in-process model cache）
  - src/orchestration/run_daily.py：ML scoring hook（有 champion 則打分，否則 skip）
  - tests/unit/test_model_registry.py：12 cases（mock DB + mock pCloud）
  - tests/unit/test_predictor.py：8 cases（module-level pickle-safe stub）
  - 152 tests pass
- 遇到的卡點：test_predictor 中 local class 無法 joblib pickle → 改用 module-level stub class
- 下次繼續：Phase 5d（SHAP Explainer，feat/phase5d-shap）

## 2026-04-22 (Phase 5b)
- 啟動時所在 branch：feat/phase5b-lightgbm-trainer
- 完成的子任務：Phase 5b 全部（5b.1–5b.7）
  - requirements.txt：lightgbm>=4.0.0、scikit-learn>=1.3.0（已存在，確認）
  - src/signals/labeler.py：compute_forward_return、binary_label（已存在，確認）
  - src/signals/trainer.py：walk_forward_split、train、save_model（已存在，確認）
  - docker/trainer.Dockerfile：新增 LightGBM trainer image
  - compose/docker-compose.yml：新增 quant-trainer service（profiles: jobs）
  - tests/unit/test_labeler.py：7 cases（forward return + binary label）
  - tests/unit/test_trainer.py：9 cases（walk_forward_split + train + save_model）
  - 132 tests pass
- 遇到的卡點：無
- 下次繼續：Phase 5c（Model Registry，feat/phase5c-model-registry）

## 2026-04-21 23:15
- 啟動時所在 branch：develop（Phase 4 merge 後）
- 使用 agents：fin-pipeline-engineer（tech/fund/builder 實作）+ fin-test-engineer（3 個測試檔）協同
- 完成的子任務：Phase 4 TASKS.md 補標記 [x]；Phase 5a 全部（5a.1–5a.6）
  - src/features/__init__.py
  - src/features/tech_features.py: ma_return, volume_features, institutional_flow_features
  - src/features/fund_features.py: revenue_momentum, roe_feature, gross_margin_feature
  - src/features/feature_builder.py: build_feature_matrix（cross-sectional median fill）
  - tests: 28 new（tech 13 + fund 10 + builder 5），116 total pass
- 遇到的卡點：test_gm_basic array length mismatch，立即修正
- 下次繼續：Phase 5b（LightGBM Trainer，feat/phase5b-lightgbm-trainer）

## 2026-04-21 22:30
- 啟動時所在 branch：develop（接續 Phase 3 merge 後）
- 使用 agents：fin-pipeline-engineer（主實作）+ fin-test-engineer（測試）協同
- 完成的子任務：Phase 4 全部（4.1–4.8）
  - src/monitoring/coverage_checker.py（4 個純函式）
  - src/registry/retrain_gate.py（should_trigger_retrain、build_retrain_decision）
  - tests/unit/test_coverage_checker.py（12 cases）+ test_retrain_gate.py（9 cases）
  - src/orchestration/run_daily.py：串入 coverage check + write coverage_snapshot.json / retrain_decision.json
  - src/ui/app.py：Coverage 頁強化（metrics、折線圖、缺件名單、retrain gate 狀態）
  - compose/grafana/.../coverage-health.json（5 panels）
  - 88 unit tests pass
- 遇到的卡點：run_daily.py 整合改為 proxy coverage（避免重複 data fetch），真實覆蓋率需 sync 後再算
- 下次繼續：Phase 5a（feature engineering，feat/phase5a-feature-engineering）

## 2026-04-21 21:00
- 啟動時所在 branch：feat/phase3-supabase（含 ghost rebase 狀態，已清除）
- 完成的子任務：Phase 3 全部（3.1–3.11）
  - src/database/: client.py, crud.py, schema.sql, __init__.py
  - src/orchestration/run_daily.py: Supabase start/finish/artifact/candidate 寫入
  - src/ui/app.py: 6 頁面（Home/Runs/庫存股/Coverage/Reports/Run Control）
  - Grafana PostgreSQL datasource + pipeline-health dashboard
  - scripts/linux/apply_schema.sh + docs/supabase-setup.md
  - 67 unit tests pass
- 遇到的卡點：gh auth login 未完成，PR 尚未建立
- 下次繼續：gh auth login 後執行 gh pr create，然後 Phase 4（coverage checker）

## 2026-04-21 16:30
- 啟動時所在 branch：develop
- 完成的子任務：Phase 0 驗收（docker build、compose config）、Phase 2 全部（2.1–2.14）
- 遇到的卡點：pCloud 真實 API 無 token，保留 mock fallback；2.8 整合測試 skipif
- 下次繼續：Phase 3（feat/phase3-supabase，需要 Supabase credentials）

## 2026-04-21 15:35
- 啟動時所在 branch：main
- 完成的子任務：Phase -1.1（建立 develop 分支）、-1.2（更新 .gitignore）、-1.3（BLOCKED 模板）、-1.4（工作紀錄）、-1.5（PR 模板）、-1.6（驗收 commit）
- 遇到的卡點：無
- 下次繼續：Phase 0（feat/phase0-docker-skeleton）
