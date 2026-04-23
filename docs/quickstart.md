# Quickstart

## 前置條件

- Python 3.11+
- Docker Desktop（Windows）或 Docker Engine（Linux）
- `gh` CLI（自動 merge 需要）：`sudo apt install gh` 或 `winget install GitHub.cli`

## 1. Clone 與環境設定

```bash
git clone https://github.com/hank716/quant_trading.git fin
cd fin
cp env.example .env.local   # 本專案只用 .env.local，填完不要 commit
```

最少只需設定 `USE_MOCK_DATA=1` 就能跑 smoke test；完整 pipeline 需要 `FINMIND_TOKEN`、`GROQ_API_KEY`、`DISCORD_WEBHOOK_URL_USER_A` 等，見 [env-variables.md](env-variables.md)。

## 2. 安裝套件並跑單元測試

```bash
pip install -r requirements.txt
pytest -q -m "not integration"
```

## 3. 首次 bootstrap Qlib 歷史資料

`qlib_ext/workflows/daily_lgbm.yaml` 訓練視窗是 2020-01-01 ~ 2022-06-30。第一次必須抓足 ~3 年資料：

```bash
python -m app.orchestration.sync_qlib_data --lookback-days 900
```

這步會把 TWSE/TPEx 全市場的價格、月營收、財務資料 dump 成 Qlib bin 格式，寫到 `workspace/qlib_data/`。之後每日 run 內建 `lookback_days=5` 增量同步。

## 4. 每日執行

```bash
# 主流程：sync → qrun → selector → explainer → Discord → Supabase
python -m app.orchestration.run_daily --profile user_a

# 單獨觸發 selector+explainer（需已有 MLflow run）
python -m app.orchestration.run_daily --profile user_a --skip-sync --skip-train

# 手動觸發訓練
python -m app.orchestration.run_training --workflow qlib_ext/workflows/daily_lgbm.yaml
```

## 5. Streamlit UI

```bash
streamlit run app/ui/app.py
# 預設 http://localhost:8501
```

若 `config/auth_users.yaml` 不存在，會進入 dev 模式（profile=user_a，不需登入）。要啟用登入，複製 `config/auth_users.yaml.example` 並填 bcrypt hash：

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
```

## 6. Docker 啟動（容器版 UI）

```bash
docker build -f docker/app.Dockerfile -t fin-app:test .
docker build -f docker/ui.Dockerfile  -t fin-ui:latest .
./scripts/linux/start_services.sh      # Linux/WSL
.\scripts\windows\start_services.ps1   # Windows PowerShell
```

| 服務 | URL |
|------|-----|
| Streamlit UI | http://localhost:8501 |

## 7. Supabase（選用）

若要啟用 DB 狀態追蹤（pipeline_runs / candidates / coverage），見 [`supabase-setup.md`](supabase-setup.md)。未設定 `SUPABASE_URL` 時自動使用 mock mode，不影響主流程。

## 常見問題

| 問題 | 解決方式 |
|------|---------|
| TLS 憑證錯誤（TWSE） | `.env.local` 加 `OFFICIAL_TLS_INSECURE_FALLBACK=true` |
| qrun 找不到資料 | 確認已跑過首次 `sync_qlib_data --lookback-days 900`；檢查 `workspace/qlib_data/features/` |
| LLM 沒有被呼叫 | 檢查 log 應出現 `Selector: groq (llm_call=True)`；若出現 `llm_call=False` 表示 `SELECTION_PROVIDER` 未設或 API key 缺 |
| pCloud 未設定 | 自動 mock mode，不影響主流程 |
| Docker 權限（Linux）| `sudo usermod -aG docker $USER` 後重新登入 |

## Workspace 目錄

```
workspace/
├── hotdata/       # 資料快取（gitignored）
├── qlib_data/     # Qlib bin 格式資料（gitignored）
├── qlib_data_csv/ # Qlib bin 的中間 CSV（gitignored）
├── mlruns/        # MLflow 追蹤（gitignored）
├── runs/          # 每次執行的 artifacts（gitignored）
├── outputs/       # 報告輸出（gitignored）
├── logs/          # 日誌（gitignored）
└── tmp/           # 暫存（gitignored）
```

## Roadmap：Phase 10.9 Shadow Run

Phase 10 程式碼已完成（新 `app.orchestration.run_daily` 是 prod 路徑）。下一步是 shadow validation：**連跑 3 天** legacy 和 new pipeline，比對 Top-20 重疊率（目標 ≥ 70%）與 score correlation（目標 ≥ 0.6）。比對結果寫到 `docs/phase10-shadow-report.md`，通過後打 `v1.0-qlib-cutover` tag，進入 Phase 11 刪 legacy。
