# Quickstart

## 前置條件

- Python 3.11+
- Docker Desktop（Windows）或 Docker Engine（Linux）
- `gh` CLI（自動 merge 需要）：`sudo apt install gh` 或 `winget install GitHub.cli`

## 1. Clone 與環境設定

```bash
git clone https://github.com/hank716/quant_trading.git fin
cd fin
cp env.example .env.local
# 填入必要的 key（最少只需 USE_MOCK_DATA=1 就能跑）
```

## 2. 本機開發（不用 Docker）

```bash
pip install -r requirements.txt

# mock 模式（不需任何 API key）
python main.py --profile user_a --use-mock-data --skip-discord

# 跑單元測試
pytest -q -m "not integration"
```

## 3. Docker 啟動服務

```bash
# Build images（第一次或 requirements.txt 更新後）
docker build -f docker/app.Dockerfile -t fin-app:test .
docker build -f docker/ui.Dockerfile  -t fin-ui:latest .

# 驗證 compose 設定
docker compose -f compose/docker-compose.yml config

# 啟動 UI + Prometheus + Grafana
./scripts/linux/start_services.sh      # Linux/WSL
.\scripts\windows\start_services.ps1   # Windows PowerShell
```

| 服務 | URL | 帳密 |
|------|-----|------|
| Streamlit UI | http://localhost:8501 | — |
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |

## 4. 執行分析工作

```bash
# 同步市場資料（盤後執行）
./scripts/linux/run_sync.sh

# 執行每日選股分析
./scripts/linux/run_daily.sh

# 同步財報（每週一次，慢速）
./scripts/linux/run_financials.sh
```

## 5. Supabase 設定（Phase 3+）

如需啟用 DB 狀態追蹤與 Grafana 連線，見 [`supabase-setup.md`](supabase-setup.md)。  
若未設定 `SUPABASE_URL`，系統自動使用 mock mode，不影響主流程。

## 常見問題

| 問題 | 解決方式 |
|------|---------|
| TLS 憑證錯誤 | `.env.local` 加 `OFFICIAL_TLS_INSECURE_FALLBACK=true` |
| pCloud 未設定 | 自動 mock mode，不影響主流程 |
| Docker 權限（Linux）| `sudo usermod -aG docker $USER` 後重新登入 |
| UI 無法連線 | 確認 port 8501 未被佔用，或 `docker logs fin-quant-ui` |

## Workspace 目錄

```
workspace/
├── hotdata/   # 資料快取（gitignored）
├── runs/      # 每次執行的 artifacts（gitignored）
├── outputs/   # 報告輸出（gitignored）
├── logs/      # 日誌（gitignored）
└── tmp/       # 暫存（gitignored）
```
