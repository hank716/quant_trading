# 環境變數參考

複製 `env.example` 為 `.env.local`（本機用）或 `.env`（相容舊版）後填入。

## Core

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `USE_MOCK_DATA` | `0` | `1` = 使用 mock 資料，不需 API key |
| `CACHE_DIR` | `.cache` | 資料快取根目錄（Docker 內建議 `/app/workspace/hotdata`） |
| `OUTPUT_DIR` | `outputs` | 報告輸出根目錄（Docker 內建議 `/app/workspace/outputs`） |
| `LOG_DIR` | *(未使用)* | 日誌根目錄（Docker 內 `/app/workspace/logs`） |
| `DATA_PROVIDER` | `official_hybrid` | `finmind` 或 `official_hybrid` |

## 資料來源

| 變數 | 說明 |
|------|------|
| `FINMIND_TOKEN` | FinMind API token（使用 finmind provider 時必填） |
| `OFFICIAL_TLS_INSECURE_FALLBACK` | `true` = 忽略 TWSE/TPEx TLS 憑證錯誤 |

## LLM

| 變數 | 說明 |
|------|------|
| `GROQ_API_KEY` | Groq API key |
| `GROQ_BASE_URL` | Groq base URL，預設 `https://api.groq.com/openai/v1` |
| `GROQ_MODEL` | 使用的模型 ID |
| `LLM_SAFE_MODE` | `true` = selector/explainer 共用 LLM 時自動降級 explainer |
| `LLM_CACHE_ENABLED` | `true` = 啟用 LLM 回應快取 |
| `ANTHROPIC_API_KEY` | Anthropic API key（Phase 2+） |

## Discord

| 變數 | 說明 |
|------|------|
| `DISCORD_WEBHOOK_URL_USER_A` | User A 的 Discord webhook |
| `DISCORD_WEBHOOK_URL_USER_B` | User B 的 Discord webhook |

## pCloud（Phase 2+）

| 變數 | 說明 |
|------|------|
| `PCLOUD_TOKEN` | pCloud API token |
| `PCLOUD_REGION` | `eu` 或 `us` |
| `PCLOUD_ROOT_FOLDER` | pCloud 根目錄路徑 |

## Supabase（Phase 3+）

| 變數 | 說明 |
|------|------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon key（唯讀查詢） |
| `SUPABASE_SERVICE_KEY` | Supabase service key（後端寫入用） |
| `SUPABASE_DB_HOST` | 直連 DB hostname（Grafana datasource 用），格式：`db.<id>.supabase.co` |
| `SUPABASE_DB_PORT` | 直連 DB port，預設 `5432` |
| `SUPABASE_DB_NAME` | 資料庫名稱，預設 `postgres` |
| `SUPABASE_DB_USER` | 資料庫使用者，預設 `postgres` |
| `SUPABASE_DB_PASSWORD` | 資料庫密碼（Supabase Settings → Database） |

詳細部署步驟見 [`docs/supabase-setup.md`](supabase-setup.md)。
