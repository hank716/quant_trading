# Supabase Setup Guide

## 前置條件

- Supabase 帳號（[app.supabase.com](https://app.supabase.com)）
- psql client（`sudo apt install postgresql-client`）

## 步驟

### 1. 建立 Supabase 專案

1. 登入 Supabase，點「New project」
2. 記下專案的 **URL** 和 **API Keys**（Settings → API）
3. Service key 用於後端寫入；anon key 用於唯讀查詢

### 2. 設定環境變數

編輯 `.env.local`（或 `.env`）：

```bash
SUPABASE_URL=https://<project-id>.supabase.co
SUPABASE_ANON_KEY=<anon-key>
SUPABASE_SERVICE_KEY=<service-role-key>

# Grafana PostgreSQL datasource（Settings → Database → Connection string）
SUPABASE_DB_HOST=db.<project-id>.supabase.co
SUPABASE_DB_PORT=5432
SUPABASE_DB_NAME=postgres
SUPABASE_DB_USER=postgres
SUPABASE_DB_PASSWORD=<database-password>
```

### 3. 套用 Schema

取得 Connection string（Settings → Database → URI）：

```bash
export DATABASE_URL="postgresql://postgres:<password>@db.<project-id>.supabase.co:5432/postgres"
bash scripts/linux/apply_schema.sh
```

執行後應看到一系列 `CREATE TABLE` 和 `CREATE INDEX` 訊息。

### 4. 驗證

```bash
psql "$DATABASE_URL" -c "\dt"
# 應列出：pipeline_runs, run_steps, run_artifacts, coverage_snapshots,
#         model_versions, model_promotions, daily_candidates, daily_positions,
#         daily_trades, daily_reports_index, system_alerts
```

### 5. 執行整合測試

```bash
pytest tests/integration/test_supabase_real.py -v
```

## 日常維護

| 操作 | 指令 |
|------|------|
| 重新套用 schema（冪等） | `bash scripts/linux/apply_schema.sh` |
| 查看最近 runs | `psql $DATABASE_URL -c "SELECT run_id, trade_date, status FROM pipeline_runs ORDER BY started_at DESC LIMIT 10;"` |
| 清除測試資料 | `psql $DATABASE_URL -c "DELETE FROM pipeline_runs WHERE run_id LIKE 'test_%';"` |

## Grafana 連線

Grafana datasource 設定檔已預先寫入 `compose/grafana/provisioning/datasources/postgres.yml`。
啟動服務後，環境變數 `SUPABASE_DB_*` 會自動注入。Dashboard 在 `compose/grafana/provisioning/dashboards/pipeline-health.json`。
