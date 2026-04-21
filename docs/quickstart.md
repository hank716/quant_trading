# Quickstart

## 1. Clone & 設定環境

```bash
git clone https://github.com/hank716/quant_trading.git fin
cd fin
cp env.example .env.local
# 編輯 .env.local，填入必要的 key（最少需要 FINMIND_TOKEN 或設 USE_MOCK_DATA=1）
```

## 2. 本機開發（不用 Docker）

```bash
pip install -r requirements.txt

# mock 模式測試（不需 API）
python main.py --profile user_a --use-mock-data --skip-discord

# 跑測試
pytest -q
```

## 3. Docker 啟動服務

```bash
# Build images（第一次或依賴更新後）
docker build -f docker/app.Dockerfile -t fin-app:test .
docker build -f docker/ui.Dockerfile -t fin-ui:latest .

# 啟動 UI + Prometheus + Grafana
./scripts/linux/start_services.sh   # Linux
# 或
.\scripts\windows\start_services.ps1  # Windows PowerShell

# 服務入口
# UI:         http://localhost:8501
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000 (admin/admin)
```

## 4. 執行分析工作

```bash
# 同步市場資料
./scripts/linux/run_sync.sh

# 執行每日分析
./scripts/linux/run_daily.sh

# 同步財報（每週執行一次即可）
./scripts/linux/run_financials.sh
```

## 5. 常見問題

- **TLS 錯誤**：在 `.env.local` 設定 `OFFICIAL_TLS_INSECURE_FALLBACK=true`
- **pCloud 未設定**：系統自動使用 mock mode，不影響主流程
- **Docker 權限**：Linux 需要 `sudo usermod -aG docker $USER` 後重新登入
