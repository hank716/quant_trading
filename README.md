# fin — 台股量化研究工作站

個人台股選股系統。每日分析 TWSE/TPEx 全市場 (~2000 檔)，透過規則過濾、量化訊號、選用 LLM 說明，產生投資候選清單與研究報告。

## 系統架構

```
每日 pipeline
  UniverseBuilder → FilterEngine → SignalEngine → Selector → Explainer
      ↓                                                          ↓
  ArtifactWriter (parquet + json)              ReportRenderer (Markdown/HTML)
      ↓                                                          ↓
  SupabaseClient (pipeline state)            DiscordNotifier (webhook)
      ↓
  PCloudClient (cold artifact storage)

UI / 監控
  Streamlit  → 控制台（Run 觸發、候選標的、庫存股管理）
  Grafana    → Pipeline health dashboard（連接 Supabase PostgreSQL）
  Prometheus → 服務監控
```

## 快速開始

```bash
git clone https://github.com/hank716/quant_trading.git fin
cd fin
cp env.example .env.local    # 填入需要的 keys
pip install -r requirements.txt

# mock 模式驗證（不需要任何 API key）
python main.py --profile user_a --use-mock-data --skip-discord

# 跑測試
pytest -q -m "not integration"
```

完整設定請見 [`docs/quickstart.md`](docs/quickstart.md)。

## Docker 服務

```bash
# Build
docker build -f docker/app.Dockerfile -t fin-app:test .
docker build -f docker/ui.Dockerfile  -t fin-ui:latest .

# 啟動 UI + Prometheus + Grafana
./scripts/linux/start_services.sh

# 服務入口
# Streamlit UI: http://localhost:8501
# Grafana:      http://localhost:3000  (admin / admin)
# Prometheus:   http://localhost:9090
```

## 每日操作

```bash
# 同步市場資料（每日盤後執行）
./scripts/linux/run_sync.sh

# 執行選股分析
./scripts/linux/run_daily.sh

# 同步財報（每週或每天一次，慢速不佔 quota）
./scripts/linux/run_financials.sh
```

## 環境變數

完整參考見 [`docs/env-variables.md`](docs/env-variables.md)。最低要求：

| 模式 | 需要的變數 |
|------|-----------|
| Mock 模式 | `USE_MOCK_DATA=1`（已在 env.example） |
| 真實資料 | `DATA_PROVIDER=official_hybrid`，TLS 問題加 `OFFICIAL_TLS_INSECURE_FALLBACK=true` |
| LLM 選股 | `GROQ_API_KEY=...` |
| pCloud 儲存 | `PCLOUD_TOKEN=...`（Phase 2+，無設定則自動 mock） |
| Supabase DB | `SUPABASE_URL=...` + `SUPABASE_SERVICE_KEY=...`（Phase 3+） |

## 開發進度

| Phase | 說明 | 狀態 |
|-------|------|------|
| 0 | Docker 基礎盤、Workspace 結構 | ✅ 完成 |
| 1 | 現有 CLI 工具容器化 | ✅ 完成 |
| 2 | Artifact-first 重構（parquet schemas、pCloud） | ✅ 完成 |
| 3 | Supabase 控制面、Streamlit UI、Grafana | ✅ 完成 |
| 4 | Coverage Checker 與 Retrain Gate | 🔲 待開始 |
| 5 | 模型平台化（LightGBM + SHAP） | 🔲 待開始 |

詳細子任務見 [`TASKS.md`](TASKS.md)。

## 文件索引

| 文件 | 說明 |
|------|------|
| [`CLAUDE.md`](CLAUDE.md) | Claude Code 架構參考（模組表、pipeline 流程、git 規則） |
| [`TASKS.md`](TASKS.md) | 開發任務清單（Claude Code 工作指令） |
| [`docs/quickstart.md`](docs/quickstart.md) | 5 分鐘上手指南 |
| [`docs/env-variables.md`](docs/env-variables.md) | 所有環境變數說明 |
| [`docs/supabase-setup.md`](docs/supabase-setup.md) | Supabase schema 部署指南 |
| [`docs/windows-task-scheduler-setup.md`](docs/windows-task-scheduler-setup.md) | Windows 排程設定 |
| [`docs/decisions/`](docs/decisions/) | Architecture Decision Records (ADR) |
| [`CLAUDE_CODE_SETUP.md`](CLAUDE_CODE_SETUP.md) | Claude Code 首次設定指南 |
