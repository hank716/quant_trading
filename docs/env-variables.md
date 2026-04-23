# 環境變數參考

**本專案只用 `.env.local`**。複製 `env.example` 為 `.env.local` 後填入——不要 commit。

```bash
cp env.example .env.local
```

所有 Phase 10+ 的新 entry point（`app.orchestration.*`、Docker compose）都只讀 `.env.local`。Legacy `main.py` 同時相容 `.env` 作為 fallback，但新用戶一律只寫 `.env.local`。

## Core

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `USE_MOCK_DATA` | `0` | `1` = 使用 mock 資料，不需 API key |
| `CACHE_DIR` | `./workspace/hotdata` | 資料快取根目錄 |
| `OUTPUT_DIR` | `./workspace/outputs` | 報告輸出根目錄 |
| `LOG_DIR` | `./workspace/logs` | 日誌根目錄 |
| `DATA_PROVIDER` | `official_hybrid` | `finmind` 或 `official_hybrid` |

## 資料來源

| 變數 | 說明 |
|------|------|
| `FINMIND_TOKEN` | FinMind API token（使用 finmind provider 時必填） |
| `OFFICIAL_TLS_INSECURE_FALLBACK` | `true` = 忽略 TWSE/TPEx TLS 憑證錯誤 |
| `OFFICIAL_TLS_INSECURE_FALLBACK_HOSTS` | 套用上述 fallback 的 host 清單（逗號分隔） |

## LLM

選股（Selector）與說明（Explainer）可以分別設定 provider，兩者互相獨立。

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `SELECTION_PROVIDER` | `rule_based` | 候選挑選的 provider：`rule_based` / `groq` / `openai_compatible` / `none` |
| `LLM_PROVIDER` | `rule_based` | 中文論述 explainer 的 provider（同上列可選值） |
| `LLM_SAFE_MODE` | `true` | `true` = 當 selector 與 explainer 使用相同外部 LLM 時，自動把 explainer 降級為 `rule_based`，每日只打 1 次 API |
| `LLM_MIN_INTERVAL_SECONDS` | `3` | 同進程兩次 LLM 呼叫之間最少間隔秒數（避免 rate limit） |
| `LLM_MAX_RETRIES` | `4` | 429 / 5xx 時最多重試次數 |
| `LLM_RETRY_BACKOFF_SECONDS` | `2` | 重試退避的基礎秒數（指數退避） |
| `LLM_CACHE_ENABLED` | `true` | `true` = 啟用 LLM 回應 SHA256 快取 |
| `LLM_CACHE_DIR` | `.cache/llm` | LLM 回應快取目錄 |

### Groq

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `GROQ_API_KEY` | — | Groq API key（selector/explainer 設為 `groq` 時必填） |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | Groq OpenAI-compatible 端點 |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Groq 使用的模型 ID |

### 其他 OpenAI-compatible provider

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `LLM_API_KEY` | — | OpenAI-compatible API key |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | API 端點 |
| `LLM_MODEL` | `gpt-4o-mini` | 使用的模型 ID |
| `ANTHROPIC_API_KEY` | — | 若日後接 Anthropic 使用 |

## Discord

| 變數 | 說明 |
|------|------|
| `DISCORD_WEBHOOK_URL_DEFAULT` | Default profile 的 webhook |
| `DISCORD_WEBHOOK_URL_USER_A` | User A 的 webhook |
| `DISCORD_WEBHOOK_URL_USER_B` | User B 的 webhook |

Profile YAML 裡的 `discord.webhook_url_env` 會指定要讀哪個環境變數。

## pCloud（Phase 2+）

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `PCLOUD_TOKEN` | — | pCloud API token（未設定則自動 mock） |
| `PCLOUD_REGION` | `eu` | `eu` 或 `us` |
| `PCLOUD_ROOT_FOLDER` | `/fin-quant` | pCloud 根目錄 |

## Supabase（Phase 3+）

| 變數 | 說明 |
|------|------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon key（唯讀查詢） |
| `SUPABASE_SERVICE_KEY` | Supabase service key（後端寫入用；未設定則自動 mock） |

詳細部署步驟見 [`supabase-setup.md`](supabase-setup.md)。

## MLflow（Phase 8+）

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `MLFLOW_TRACKING_URI` | `file:workspace/mlruns` | MLflow 追蹤目錄 |

## UI 認證（Phase 10+）

Streamlit authenticator 的 cookie key **不走環境變數**。它定義在 `config/auth_users.yaml` 的 `cookie.key` 欄位（已加入 `.gitignore`）。參考 `config/auth_users.yaml.example`。
