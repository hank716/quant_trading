## v12 update

- 修正 `official_hybrid` 基本資料日期格式，會把 `19620209`、`83/12/05` 這類官方格式正規化成 `YYYY-MM-DD`，避免 `listing_days` 變成 `missing`。
- `official_hybrid` 的財報行為改成 **cache-only**：`main.py` 與 `sync_data.py` 不再 live 呼叫 FinMind 財報。
- 新增 `sync_financials_slow.py`：用小批次、低頻、可續跑的方式慢慢補齊 FinMind 財報快取。
- 主流程仍會讀季度財報，但只讀 `.cache/finmind` 內已存在的快取；若快取為空，請先執行 `sync_financials_slow.py`。

### v12 建議執行方式

```bash
# 每日同步：永遠不碰 live 財報
python sync_data.py --profile user_a --data-provider official_hybrid --lookback-days 5

# 低頻慢速補財報（例如每天跑一次或每小時跑一批）
python sync_financials_slow.py --batch-size 30

# 正常跑主流程；若 strategy 有開 financial_statement，會只讀本地快取
python main.py --profile user_a --data-provider official_hybrid --stock-limit 50 --stock-limit-mode liquidity
```

> 若要先驗證 LLM/候選流程，可暫時把 `financial_statement.enabled: false`；等快取累積起來再打開。

## v11.3 update

- Fix non-trading day handling in `OfficialHybridClient.get_price_snapshot()` and institutional snapshots.
- When both TWSE and TPEx return empty data for a calendar day, the client now returns an empty DataFrame instead of raising `ValueError: No objects to concatenate`.
- This lets `sync_data.py --lookback-days N` safely span weekends and exchange holidays.

# 個人化台股選股系統 v11.2

這版是 **官方資料接入的 JSON / CSV 穩定化修正版**，重點是避免再依賴 TWSE HTML 與 `lxml`。

> v11.2 額外修正：**真正移除 TWSE HTML fallback 程式路徑**，避免在 JSON 無資料或 JSON 欄位異常時又退回 `pd.read_html()`。

## v11 主要改動

1. **TWSE 改成 JSON-only**
   - 上市日價改走 `MI_INDEX?response=json`。
   - 上市三大法人改走 `T86?response=json`。
   - 不再使用 TWSE HTML fallback，因此不需要 `pd.read_html` / `lxml`。

2. **TPEx CSV 解析改成容錯模式**
   - 上櫃日價與三大法人仍走官方 CSV。
   - 先清洗報表前言、空行、`共X筆`、註解尾段，再解析真正表頭。
   - 避免 `ParserError: Expected 1 fields in line X, saw Y`。

3. **TLS fallback host 清單補齊**
   - 預設允許：
     - `mopsfin.twse.com.tw`
     - `openapi.twse.com.tw`
     - `www.twse.com.tw`
     - `www.tpex.org.tw`

4. **`.env` 建議值**

```dotenv
OFFICIAL_TLS_INSECURE_FALLBACK=true
OFFICIAL_TLS_INSECURE_FALLBACK_HOSTS=mopsfin.twse.com.tw,openapi.twse.com.tw,www.twse.com.tw,www.tpex.org.tw
```

## v11 建議執行方式

```bash
python sync_data.py --profile user_a --data-provider official_hybrid --lookback-days 35
python main.py --profile user_a --data-provider official_hybrid --stock-limit 200 --stock-limit-mode liquidity --skip-discord
```

若你想先快速驗證 ingestion：

```bash
python sync_data.py --profile user_a --data-provider official_hybrid --lookback-days 5
```

---

# 個人化台股選股系統 v10.1

這版是 **官方資料接入的 TLS 相容性修正版**。

## v10.1 主要改動

1. **移除最容易出錯的 listed MOPS CSV 直連**
   - 上市公司基本資料改優先走 `openapi.twse.com.tw` JSON。
   - 上市公司月營收改優先走 `openapi.twse.com.tw` JSON。
   - 若 OpenAPI 暫時失敗，才退回舊的 CSV 路徑。

2. **新增官方站 TLS 相容性 fallback**
   - 遇到 `requests.exceptions.SSLError` 時，若目標 host 在允許清單內，會自動 retry 一次 `verify=False`。
   - 這是為了處理部分官方站台在 Python 3.13 / OpenSSL 下的憑證相容性問題。
   - 預設只對下列 host 啟用：
     - `mopsfin.twse.com.tw`
     - `openapi.twse.com.tw`
     - `www.tpex.org.tw`

3. **新增 `.env` 參數**

```dotenv
OFFICIAL_TLS_INSECURE_FALLBACK=true
OFFICIAL_TLS_INSECURE_FALLBACK_HOSTS=mopsfin.twse.com.tw,openapi.twse.com.tw,www.twse.com.tw,www.tpex.org.tw
```

## v10.1 建議執行方式

```bash
python sync_data.py --profile user_a --data-provider official_hybrid --lookback-days 35
python main.py --profile user_a --data-provider official_hybrid --stock-limit 200 --stock-limit-mode liquidity --skip-discord
```

若你想先確認是不是 TLS 問題，也可以只先同步：

```bash
python sync_data.py --profile user_a --data-provider official_hybrid --lookback-days 5
```

---

# 個人化台股選股系統 v10

這版的重點是 **接入官方資料源，改成適合全市場日終掃描的 mixed data pipeline**。

## v10 主要改動

1. **`--data-provider official_hybrid`**
   - 日價 / 成交量 / 成交金額：優先走官方 TWSE / TPEx 日資料。
   - 三大法人：優先走官方 TWSE / TPEx 日資料。
   - 月營收：優先走官方 MOPS OpenData 全表。
   - 財報：預設保留 FinMind fallback，避免一次把官方各產業財報格式全攤平造成維護成本過高。

2. **本地快取 + 增量回補**
   - 官方日資料會以「按交易日 cache」方式存到 `--cache-dir`。
   - 第一次跑會回補近一段 lookback 視窗；第二次之後通常只需補新的一天。

3. **新增 `sync_data.py`**
   - 可以先把資料同步到本地，再由 `main.py` 只讀快取做選股。

## v10 建議執行方式

### 直接用官方 mixed source 跑選股

```bash
python main.py --profile user_a --data-provider official_hybrid --stock-limit 200 --stock-limit-mode liquidity --skip-discord
```

### 先同步資料，再跑選股

```bash
python sync_data.py --profile user_a --data-provider official_hybrid --lookback-days 35
python main.py --profile user_a --data-provider official_hybrid --stock-limit 200 --stock-limit-mode liquidity --skip-discord
```

## `.env` 新增建議

```dotenv
DATA_PROVIDER=official_hybrid
```

> 若你希望日價 / 法人 / 月營收走官方資料，但財報仍可補 FinMind，請保留 `FINMIND_TOKEN`。

---

# 個人化台股選股系統 v9

這版的重點是 **把 `stock-limit` 改成更合理的挑法，並補上 FinMind batch 模式**。

## v9 主要改動

1. **`stock-limit-mode=liquidity`**
   - 不再只抓代號前 N 檔。
   - 會優先用最近一個交易日的 `Trading_money` 排序，挑最活躍的標的。
   - 你的目前持股會被保留在候選池前面，避免你自己的持股被 `stock-limit` 擋掉。

2. **最新交易日對齊**
   - 會先查 `TaiwanStockTradingDate`，再把價格/法人資料對齊到最新交易日。
   - 你在假日或盤中執行時，比較不容易出現整批 `missing latest price`。

3. **Premium batch 模式**
   - 加上 `--allow-premium-batch` 後，會優先用 FinMind 的「單日全市場資料」來抓：
     - `TaiwanStockPrice`
     - `TaiwanStockInstitutionalInvestorsBuySell`
     - `TaiwanStockMonthRevenue`
     - `TaiwanStockFinancialStatements`
   - 這樣可以大幅減少 API 呼叫數。
   - 但這需要你在 FinMind 端有對應權限。

4. **硬規則淘汰原因摘要**
   - 輸出 notes 會多出像這樣的資訊：
     - `硬規則淘汰主因：missing latest price（87 檔）`
   - 方便你直接看出是策略太嚴，還是資料其實沒抓到。

## v9 建議執行方式

### 先用更合理的 100 檔模式

```bash
python main.py --profile user_a --stock-limit 100 --stock-limit-mode liquidity --skip-discord
```

### 若你有 FinMind batch 權限，直接掃全市場

```bash
python main.py --profile user_a --allow-premium-batch --skip-discord
```

### 若你同時想限制成前 100 檔，但挑法改成流動性優先

```bash
python main.py --profile user_a --stock-limit 100 --stock-limit-mode liquidity --allow-premium-batch --skip-discord
```

---

# 個人化台股選股系統 v8

這版的重點是 **抗 rate limit**，特別是你現在用 Groq 免費額度時最容易遇到的 `429 Too Many Requests`。

## v8 主要改動

1. **LLM 安全模式**
   - 若 `selector_provider` 和 `llm_provider` 都是同一個外部 provider（例如都用 `groq`），預設只會讓 selector 打外部 LLM。
   - 說明層會自動改成 `rule_based`，避免同一輪連打兩次 API。
   - 可用 `--force-llm-explainer` 強制開啟第二次 LLM 呼叫。

2. **Retry / Backoff / Throttle**
   - 遇到 429、500、502、503、504 這類暫時性錯誤，會自動重試。
   - 會讀 `Retry-After`，若對方有回傳就照著等。
   - 同一進程內兩次 LLM 請求之間，預設至少間隔 `3` 秒。

3. **LLM 回應快取**
   - 同一份 payload 不會重複打 API。
   - 預設快取路徑：`.cache/llm`

4. **自動 fallback**
   - selector 打 LLM 失敗：自動退回 `rule_based selector`
   - explainer 打 LLM 失敗：自動退回 `rule_based explainer`
   - 也就是說，系統不會因為 Groq 一次 429 就整個 crash。

---

## 這次你要覆蓋的檔案

如果你本地已經有 v7，只要覆蓋下面這些檔案：

```text
main.py
.env.example
README.md
llm/explainer.py
llm/selector.py
llm/openai_compat.py
tests/test_decision_system.py
```

其中 `llm/openai_compat.py` 是 **新增檔案**。

---

## v8 建議的執行方式

### 最穩定的跑法

```bash
python main.py --profile user_a --use-mock-data
```

如果 `user_a.yaml` 是：

```yaml
selector_provider: groq
llm_provider: groq
```

v8 會自動變成：
- selector: `groq`
- explainer: `rule_based`

也就是一輪只打一個 Groq API，比較不容易 429。

### 如果你真的要讓 explainer 也打 LLM

```bash
python main.py --profile user_a --use-mock-data --force-llm-explainer
```

這會關掉安全模式，改回兩次外部 LLM 呼叫。

---

## `.env` 新增的設定

請把下面幾個參數補到你的 `.env`：

```dotenv
LLM_SAFE_MODE=true
LLM_MIN_INTERVAL_SECONDS=3
LLM_MAX_RETRIES=4
LLM_RETRY_BACKOFF_SECONDS=2
LLM_CACHE_ENABLED=true
LLM_CACHE_DIR=.cache/llm
```

### 各參數用途

- `LLM_SAFE_MODE=true`
  - 預設開啟，只打最必要的外部 LLM 呼叫。
- `LLM_MIN_INTERVAL_SECONDS=3`
  - 同一進程內兩次 LLM 請求之間最少等待 3 秒。
- `LLM_MAX_RETRIES=4`
  - 遇到 429 或暫時性錯誤時最多重試 4 次。
- `LLM_RETRY_BACKOFF_SECONDS=2`
  - 第一次重試等 2 秒，之後指數退避。
- `LLM_CACHE_ENABLED=true`
  - 開啟回應快取。
- `LLM_CACHE_DIR=.cache/llm`
  - 快取目錄位置。

---

## 為什麼 v7 會撞到 429

你原本的 `user_a` profile 是：

```yaml
selector_provider: groq
llm_provider: groq
```

所以一輪流程會是：

1. 先打一次 Groq 做 selector
2. 接著又立刻打一次 Groq 做 explainer

在免費額度下，很容易第二次就被擋成 429。

v8 的處理方式是：
- 先把 API 次數壓到最低
- 真的被擋到時自動 retry
- 還是不行就自動 fallback，不讓整個程式炸掉

---

## 輸出檔名

這版不影響你原本的 dated output，仍然會輸出：

```text
outputs/user_a/daily_result_YYYYMMDD.json
outputs/user_a/daily_report_YYYYMMDD.md
```

例如：

```text
outputs/user_a/daily_result_20260417.json
outputs/user_a/daily_report_20260417.md
```

---

## 驗證方式

### 測試

```bash
pytest -q
```

### mock 模式

```bash
python main.py --profile user_a --use-mock-data --skip-discord
```

### 真實資料

```bash
python main.py --profile user_a --stock-limit 100 --skip-discord
```

---

## 建議的 Groq 使用策略

若你是個人用途，而且想盡量穩：

- `selector_provider=groq`
- `llm_provider=groq`
- `LLM_SAFE_MODE=true`

這樣你 still 可以用 Groq 來做選股判讀，但不會每次都再多打一個 explainer call。
