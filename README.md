# fin — 台股量化研究工作站

個人台股選股系統。每日分析 TWSE/TPEx 全市場（~2000 檔），以 Microsoft Qlib 模型 ranking + rule-based/LLM selector 產生候選清單，配合中文投資論述與 Discord 推播。

## 系統架構

```
每日 pipeline（app.orchestration.run_daily）
  sync_qlib_data → qrun (LightGBM) → MLflow recorder → pred.pkl
      ↓
  QlibSelector (rule_based / Groq / openai_compat) → selections
      ↓
  QlibExplainer (rule_based / Groq / openai_compat) → 中文論述
      ↓
  Discord webhook（含 IC / Rank IC / Sharpe / MDD）
      ↓
  Supabase qlib_runs（run 狀態 + metrics）

UI：Streamlit（單一網頁，6 頁 + bcrypt auth guard）
  今日報告 / 我的持股 / 策略設定 / 模型狀態 / 回測分析 / 監控 & 告警
```

> **遷移中：** Phase 6–11 正在把核心替換為 Qlib（Strangler Fig 策略）。Phase 10 已完成 cutover，legacy 預計 Phase 11 刪除。詳見 [`docs/decisions/ADR-001-qlib-integration.md`](docs/decisions/ADR-001-qlib-integration.md) 與 [`docs/architecture.md`](docs/architecture.md)。

## 快速開始

```bash
git clone https://github.com/hank716/quant_trading.git fin
cd fin
cp env.example .env.local    # 填入 keys（本專案只用 .env.local）
pip install -r requirements.txt

# 單元測試（不需任何 API key）
pytest -q -m "not integration"
```

### 首次 bootstrap Qlib bin 資料

`qlib_ext/workflows/daily_lgbm.yaml` 的訓練視窗是 **2020-01-01 ~ 2022-06-30**（~3 年）。第一次執行必須抓足夠的歷史資料才能訓出模型：

```bash
# 首次：抓 ~3 年歷史資料並 dump 成 Qlib bin 格式
python -m app.orchestration.sync_qlib_data --lookback-days 900
```

之後每天 `run_daily` 內建 `lookback_days=5` 做增量同步，不需要再抓整段歷史。

### 每日執行

```bash
# 同步 → 訓練 → selector → explainer → Discord → Supabase
python -m app.orchestration.run_daily --profile user_a

# 啟動 Streamlit UI（http://localhost:8501）
streamlit run app/ui/app.py
```

## Docker 服務

```bash
docker build -f docker/app.Dockerfile -t fin-app:test .
docker build -f docker/ui.Dockerfile  -t fin-ui:latest .
./scripts/linux/start_services.sh    # 啟動 Streamlit UI container
```

| 服務 | URL |
|------|-----|
| Streamlit UI | http://localhost:8501 |

## 環境變數

完整參考見 [`docs/env-variables.md`](docs/env-variables.md)。最低要求：

| 模式 | 需要的變數 |
|------|-----------|
| Mock smoke test | `USE_MOCK_DATA=1`（已在 env.example） |
| 真實資料 sync | `DATA_PROVIDER=official_hybrid`，TLS 問題加 `OFFICIAL_TLS_INSECURE_FALLBACK=true` |
| LLM selector | `SELECTION_PROVIDER=groq` + `GROQ_API_KEY=...` |
| LLM explainer | `LLM_PROVIDER=groq` + `GROQ_API_KEY=...`（`LLM_SAFE_MODE=true` 預設會自動降級避免重複打 API） |
| Discord 推播 | `DISCORD_WEBHOOK_URL_USER_A=...` |
| pCloud 儲存 | `PCLOUD_TOKEN=...`（選用；未設定自動 mock） |
| Supabase DB | `SUPABASE_URL=...` + `SUPABASE_SERVICE_KEY=...`（選用；未設定自動 mock） |

## 開發進度

| Phase | 說明 | 狀態 |
|-------|------|------|
| 0 | Docker 基礎盤、Workspace 結構 | ✅ 完成 |
| 1 | CLI 容器化 | ✅ 完成 |
| 2 | Artifact-first 重構（parquet schemas、pCloud） | ✅ 完成 |
| 3 | Supabase 控制面、Streamlit UI | ✅ 完成 |
| 4 | Coverage Checker 與 Retrain Gate | ✅ 完成 |
| 5 | 模型平台化（LightGBM + SHAP） | ✅ 完成 |
| 6 | Qlib 基礎 + TW 資料層 | ✅ 完成 |
| 7 | TW DataHandlers（tech / fundamental / combined） | ✅ 完成 |
| 8 | Qlib 訓練 + MLflow Registry | ✅ 完成 |
| 9 | Backtest、Strategy、Analysis | ✅ 完成 |
| **10** | **Orchestration Cutover（★）** | ✅ Code done；10.9 shadow run 需累積 3 天歷史 |
| 11 | Legacy 清理 + 文件重寫 | 🚧 待開始 |

**Phase 10.9 狀態：** 程式碼已完成，待累積 3 天 `python -m app.orchestration.run_daily` 的 MLflow 記錄後，才能跑 legacy vs new pipeline 的 Top-20 重疊率與 score correlation 比對。

詳細子任務見 [`TASKS.md`](TASKS.md)。

## Legacy 入口（Phase 11 會刪）

```bash
# mock 模式 smoke test（仍可用，但不是主路徑）
python main.py --profile user_a --use-mock-data --skip-discord
```

## 文件索引

| 文件 | 說明 |
|------|------|
| [`CLAUDE.md`](CLAUDE.md) | Claude Code 架構參考（模組表、pipeline 流程、git 規則） |
| [`TASKS.md`](TASKS.md) | 開發任務清單 |
| [`docs/architecture.md`](docs/architecture.md) | 架構全景：現況 → Qlib 目標 → Strangler Fig 時程 |
| [`docs/decisions/ADR-001-qlib-integration.md`](docs/decisions/ADR-001-qlib-integration.md) | Qlib 全面遷移架構決策 |
| [`docs/quickstart.md`](docs/quickstart.md) | 上手指南 |
| [`docs/env-variables.md`](docs/env-variables.md) | 所有環境變數說明 |
| [`docs/supabase-setup.md`](docs/supabase-setup.md) | Supabase schema 部署指南 |
| [`docs/windows-task-scheduler-setup.md`](docs/windows-task-scheduler-setup.md) | Windows 排程設定 |
| [`CLAUDE_CODE_SETUP.md`](CLAUDE_CODE_SETUP.md) | Claude Code 首次設定指南 |
