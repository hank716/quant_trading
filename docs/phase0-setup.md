# Phase 0 Setup Guide

## 服務啟動

```bash
# Linux
./scripts/linux/start_services.sh

# Windows (PowerShell)
.\scripts\windows\start_services.ps1
```

## 各服務入口

| 服務 | URL | 帳號/密碼 |
|------|-----|----------|
| Streamlit UI | http://localhost:8501 | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | admin / admin |

## 前置條件

1. 安裝 Docker Desktop（Windows）或 Docker Engine（Linux）
2. 複製 `env.example` 為 `.env.local`，填入必要的 key
3. 確認 `.env.local` 包含 `USE_MOCK_DATA=1`（Phase 0 不需要真實 API）

## Docker 操作

```bash
# 重新 build image
docker build -f docker/app.Dockerfile -t fin-app:test .
docker build -f docker/ui.Dockerfile -t fin-ui:latest .

# 驗證 compose 設定
docker compose -f compose/docker-compose.yml config

# 停止所有服務
docker compose -f compose/docker-compose.yml down
```

## 排錯

- **UI 無法連線**：確認 port 8501 未被佔用，或檢查 `docker logs fin-quant-ui`
- **TLS 錯誤**：設定 `.env.local` 中 `OFFICIAL_TLS_INSECURE_FALLBACK=true`
- **pCloud 未設定**：Phase 0 預設 mock mode，不需要真實 token

## 目錄結構

```
workspace/
├── hotdata/   # 資料快取（.gitignore）
├── runs/      # 每次執行的 artifacts（.gitignore）
├── outputs/   # 報告輸出（.gitignore）
├── logs/      # 日誌（.gitignore）
└── tmp/       # 暫存（.gitignore）
```
