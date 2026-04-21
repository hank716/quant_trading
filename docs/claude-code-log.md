# Claude Code 工作紀錄

每次啟動請在此檔最上方新增一筆：

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
