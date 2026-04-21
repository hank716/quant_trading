# 量化交易系統完整重構計畫 v7

## Windows 11 + Docker Desktop (WSL2) + 本機主算力 + pCloud API 冷資料湖 + Supabase 控制面

---

## 一、版本定位

這份 v7 是在以下前提下重寫的正式重構計畫：

- **主要運算節點**：Windows 11 主機
- **執行環境**：Docker Desktop + WSL2
- **本地儲存**：256GB SSD，只存熱資料與工作區
- **冷資料湖 / Artifact 倉庫**：pCloud（以 **API** 為主通道）
- **熱資料 / 控制平面**：Supabase PostgreSQL
- **操作型 UI**：Streamlit
- **監控型 Dashboard**：Grafana
- **監控資料來源**：Prometheus + PostgreSQL
- **Railway**：不再作為主算力平台；可完全不使用，或只保留未來遠端展示用途

這版的核心目標不是「把現在的 CLI 工具硬搬到 Docker」，而是把你現有的日終選股工具，逐步重構成：

1. 可每日穩定運作的本機批次研究系統
2. 輸出可追溯、可回放、可審計
3. 後續可平滑升級到 Qlib / LightGBM / SHAP / Auto-retrain
4. 即使本機重灌，也能從 pCloud + Supabase 重建狀態

---

## 二、最重要的架構結論

### 1. Windows 不是主要「執行環境」，而是主要「宿主與排程器」

Windows 11 的責任：

- 提供硬體資源
- 提供 Docker Desktop 與 WSL2
- 提供 Windows Task Scheduler 做定時任務
- 提供 GUI 入口與人工維運介面

真正執行 Python pipeline 的地方應是：

- **Docker 容器內的 Linux 環境**
- 程式碼與 bind-mounted 工作區放在 **WSL/Linux filesystem**

### 2. pCloud 不是掛載磁碟，而是正式冷資料湖

pCloud 的正式角色：

- 存 raw snapshots
- 存 canonical parquet
- 存 historical datasets
- 存 model artifacts
- 存 reports / manifests / logs archive
- 存 retrain outputs / shap outputs

### 3. pCloud API 為主，WebDAV 為輔

正式 pipeline 一律用 **pCloud API**：

- 上傳
- 校驗
- 查 revision
- 建立目錄
- 下載 artifacts

WebDAV 僅保留給：

- 人工檢查
- 少量手動搬檔
- 某些第三方工具相容需求

### 4. Streamlit 與 Grafana 分工明確

**Streamlit**：人用的控制台

- 今日結果
- active model 狀態
- coverage 狀態
- retrain 按鈕
- predictor 按鈕
- 手動 backfill / resync
- LLM 中文說明

**Grafana**：系統觀測與歷史監控

- 每日 pipeline runtime
- retrain success/fail trend
- container CPU / RAM
- coverage timeline
- candidate vs champion metrics trend
- errors / alert counters

### 5. 系統中心物件仍然是 `signal`

這版依然保留你前面 spec-driven 文件的主軸：

- 模型層輸出 `signal`
- 投組層輸出 `position` / `trades`
- 報告層輸出 `daily_report`
- 每次執行留下 `run_manifest`

也就是說，現在的巨石 `DailyResult` 最終會被拆成正式 artifacts，而不是一直當主輸出。

---

## 三、為什麼不用 Railway 當主執行面

本次重構正式採納以下判斷：

- 日終選股、慢速財報同步、未來 Qlib 訓練都偏向 **batch-heavy / IO-heavy / CPU-heavy**
- Docker + 本地 WSL2 對長時間訓練、磁碟快取、工作目錄掌控度更高
- Railway 更適合輕型 web service、短工作流、遠端展示，不適合做你的主要訓練與研究節點
- 本機主算力 + pCloud + Supabase 的結構，更貼近你現在的預算、效能、與成長路徑

因此這版的原則是：

> **先把本機研究系統做穩，再考慮把訓練或展示的一部分外溢到雲端。**

---

## 四、正式系統定位

### 第一階段定位

本系統第一階段是：

> **每日批次的量化研究與選股系統**

不是：

- 自動下單系統
- 高頻交易系統
- 多機叢集訓練平台

### 第一階段每天產出

- `signal.parquet`
- `today_position.csv`
- `today_trades.json`
- `daily_report.json`
- `daily_report.md`
- `run_manifest.json`
- `coverage_snapshot.json`
- `pipeline logs`

---

## 五、目標架構總覽

```text
Windows 11 Host
├── Docker Desktop (WSL2 engine)
│   ├── quant-ui           # Streamlit
│   ├── quant-monitor      # app metrics exporter (optional)
│   ├── prometheus         # metrics scrape
│   ├── grafana            # observability dashboard
│   ├── quant-daily        # one-shot daily pipeline container
│   ├── quant-sync         # one-shot sync container
│   ├── quant-financials   # one-shot slow financial backfill container
│   └── quant-trainer      # future retrain container
│
├── WSL2 filesystem
│   └── /home/hank/quant-fin/
│       ├── repo/
│       ├── workspace/
│       ├── hotdata/
│       ├── logs/
│       └── compose/
│
├── pCloud
│   ├── raw/
│   ├── bronze/
│   ├── silver/
│   ├── gold/
│   ├── models/
│   ├── reports/
│   └── manifests/
│
└── Supabase PostgreSQL
    ├── users / strategies
    ├── pipeline_runs / run_steps
    ├── coverage_snapshots
    ├── model_versions / promotions
    ├── daily_candidates / positions / trades
    └── report_index / alerts
```

---

## 六、責任分層

## 6.1 Windows Host

責任：

- 安裝 Docker Desktop
- 啟用 WSL2 backend
- 排程 `docker compose run --rm ...` 任務
- 存放 Docker Desktop 設定
- 提供人工操作入口

不負責：

- 直接跑主要 Python 處理邏輯
- 直接承接大型研究資料目錄
- 把 `C:\` 當成主要 bind mount 工作區

## 6.2 WSL2 / Linux filesystem

責任：

- 放 repo
- 放 compose 檔
- 放 bind-mounted 熱資料與工作區
- 放容器共用 log / outputs / tmp

建議路徑：

```text
/home/hank/quant-fin/
  repo/
  workspace/
  hotdata/
  logs/
  compose/
```

## 6.3 Docker Containers

責任：

- 執行所有 Python pipeline
- 執行 UI / metrics / monitoring
- 執行未來的 retrain job

## 6.4 pCloud

責任：

- 冷資料湖
- artifacts 正式保存
- 備援與回放資料來源

## 6.5 Supabase

責任：

- 系統狀態
- 控制平面
- 使用者設定
- pipeline metadata
- coverage / model registry metadata
- Dashboard 查詢來源

---

## 七、部署原則

### 7.1 一律使用 Docker Desktop 的 WSL2 backend

### 7.2 所有 bind-mounted 程式碼與資料都放 Linux filesystem

不要：

- 把 repo 放在 `C:\Users\...`
- 把主要 working directory 放在 `/mnt/c/...`
- 讓高頻 IO 與 watch/reload 依賴 Windows filesystem

### 7.3 工作資料與冷資料分離

- **本機 SSD**：只放熱資料 / 當下工作資料 / 最近 rolling window
- **pCloud**：放可追溯的正式 artifacts 與歷史資料

### 7.4 長時運算與 UI 分離

- Trainer 不和 Streamlit 同容器
- Daily pipeline 不和 UI 同容器
- Monitoring stack 不和 ETL / training 同容器

---

## 八、儲存分層設計

## 8.1 本機 SSD（熱資料）

只保留：

- 最近 3–5 年 rolling window
- active model
- predictor 當日所需的 feature slice
- 最近一段 run logs
- Docker volume / local caches
- 尚未上傳 pCloud 的暫存 artifacts

## 8.2 pCloud（冷資料湖）

### 正式保存目錄

```text
/raw/
/bronze/
/silver/
/gold/
/models/
/reports/
/manifests/
/shap/
/log-archive/
/backups/
```

### 保存內容

- 原始日價、法人、營收、財報快照
- canonical / bronze / silver / gold parquet
- model artifacts
- shap outputs
- daily reports
- run manifests
- monthly backups

## 8.3 Supabase（控制面與索引）

只存：

- metadata
- 狀態
- 指標
- artifact URI
- 使用者策略
- 當日候選與交易摘要

不存：

- 大型 parquet
- shap row-level dumps
- model binaries
- 原始報表全文大檔

---

## 九、pCloud 使用策略

## 9.1 正式通道：pCloud API

正式 pipeline 只透過 `pcloud_client.py` 連 pCloud API：

- 建資料夾
- 上傳檔案
- checksum 驗證
- revision 查詢
- 下載檔案
- stat metadata

## 9.2 輔助通道：WebDAV

只用於：

- 人工瀏覽
- 少量拖拉檔案
- 外部工具臨時相容

不建議：

- 當正式 ETL 寫入路徑
- 當 trainer / predictor 的工作目錄
- 當大量長時間同步主通道

## 9.3 檔案命名規則

一律 immutable path：

```text
/raw/market=tw/source=official_hybrid/date=2026-04-20/snapshot_id=abc123/price.parquet
/raw/market=tw/source=official_hybrid/date=2026-04-20/snapshot_id=abc123/flow.parquet
/bronze/market=tw/dataset=price/data_ver=20260420_abcd/part-000.parquet
/silver/featureset=tech_v1/date=2026-04-20/part-000.parquet
/gold/featureset=unified_v1/data_ver=20260420_abcd/split=test/part-000.parquet
/models/family=alpha_5d/model_ver=20260420_abcd/model.txt
/reports/date=2026-04-20/run_id=xyz789/daily_report.json
/manifests/date=2026-04-20/run_id=xyz789/run_manifest.json
```

不能再用：

- `active_model.pkl` 直接覆蓋
- `latest_report.json` 直接覆蓋
- `current_data.parquet` 直接覆蓋

---

## 十、Supabase 資料表設計

至少需要以下幾組表：

### 10.1 使用者與策略

- `users`
- `user_strategy`
- `user_holdings`

### 10.2 Pipeline 狀態

- `pipeline_runs`
- `run_steps`
- `run_artifacts`
- `system_alerts`

### 10.3 資料完整度

- `coverage_snapshots`
- `coverage_missing_items`

### 10.4 模型與 promotion

- `model_versions`
- `model_metrics`
- `model_promotions`
- `retrain_decisions`

### 10.5 每日輸出

- `daily_candidates`
- `daily_positions`
- `daily_trades`
- `daily_reports_index`

### 10.6 監控摘要（可選）

- `job_runtime_daily`
- `job_failures_daily`
- `resource_summary_daily`

---

## 十一、Dashboard 設計

## 11.1 Streamlit：操作型 UI

頁面建議：

### 首頁 Dashboard

- 最新交易日
- 今日 pipeline 狀態
- 今日 signal / candidates / trades 摘要
- active model version
- latest coverage snapshot

### 模型頁

- champion model
- candidate model
- metrics history
- recent promotions
- retrain triggers

### Coverage 頁

- 當月營收 coverage
- 當季財報 coverage
- 缺件名單
- 權值股覆蓋狀態

### Run 控制頁

- 手動觸發 sync
- 手動觸發 daily run
- 手動觸發 retrain
- 重新上傳 report
- 重新產生 manifest

### 報告頁

- 每日 report markdown
- 原始 JSON
- LLM 生成時間 / provider / model

## 11.2 Grafana：監控型 UI

Dashboard 建議：

### Pipeline Health

- daily job runtime
- sync runtime
- financial backfill runtime
- success / fail counts

### Resource Usage

- CPU usage per container
- memory usage per container
- disk usage trend
- Docker host load

### Data Health

- latest trade date freshness
- coverage progression
- missing filings count
- sync lag

### Model Health

- champion valid metric trend
- retrain triggers over time
- candidate acceptance / rejection

---

## 十二、Prometheus / Metrics 設計

## 12.1 Prometheus 抓哪些資料

### 容器層

- CPU usage
- memory usage
- restart count
- disk / volume usage

### 應用層

- `job_runtime_seconds{job="daily"}`
- `job_status{job="daily"}`
- `coverage_ratio{type="revenue"}`
- `coverage_ratio{type="financial"}`
- `candidate_count`
- `trade_count`
- `report_generation_seconds`

### 事件層

- `retrain_trigger_total`
- `retrain_success_total`
- `retrain_fail_total`
- `pcloud_upload_fail_total`
- `llm_report_fallback_total`

## 12.2 PostgreSQL 給 Grafana 查什麼

- active model version
- latest coverage snapshot
- last successful daily run
- latest trades summary
- report index
- promotion history

---

## 十三、Windows 版服務拓樸

## 13.1 長駐容器

### `quant-ui`

- Streamlit UI
- Port 8501

### `prometheus`

- scrape metrics
- Port 9090

### `grafana`

- visualize metrics and PostgreSQL data
- Port 3000

### `cadvisor`（可選）

- 容器資源 metrics

## 13.2 非長駐容器（one-shot job）

### `quant-sync`

- 同步日價 / 法人 / 營收
- 跑完即退出

### `quant-financials`

- 慢速補財報
- 跑完即退出

### `quant-daily`

- 產生 candidates / report / notifications
- 跑完即退出

### `quant-trainer`

- 未來 LightGBM / Qlib retrain
- 跑完即退出

---

## 十四、排程設計

## 14.1 正式排程工具

使用：

- **Windows Task Scheduler**

不使用：

- 常駐 APScheduler giant process
- Streamlit container 內偷跑 background scheduler

## 14.2 建議排程

### 平日

- 16:35 `quant-sync`
- 17:00 `quant-financials`（輕量檢查或補件）
- 17:10 `quant-daily`
- 18:00 optional report archive / pCloud verify

### 每小時

- `quant-financials` 小批次 backfill

### 每週六

- `quant-trainer`（條件達標才真正重訓）

### 每月

- cleanup hot cache
- archive logs to pCloud
- verify pCloud manifest consistency

## 14.3 排程執行方式

Task Scheduler 呼叫 PowerShell：

- `docker compose run --rm quant-sync ...`
- `docker compose run --rm quant-daily ...`
- `docker compose run --rm quant-financials ...`

長駐服務則用：

- `docker compose up -d quant-ui prometheus grafana cadvisor`

---

## 十五、現有 repo 對應的重構方向

你現在的 repo 不是空白專案，而是已有可工作的日終選股工具。v7 不是推翻，而是重構。

## 15.1 建議保留

- `official_hybrid_client.py`
- `finmind_client.py`（若還要 fallback）
- `sync_data.py`
- `sync_financials_slow.py`
- `decision.py` / rules engine 相關邏輯
- `llm_selector.py`
- `report.py`
- 測試資料與 mock 資料

## 15.2 優先拆分

### 現有 `main.py`

拆成：

- `run_daily.py`
- `run_signal.py`
- `run_report.py`
- `run_notify.py`

### 設定管理

- `config_loader.py` 改為 `config/` + typed settings

### Cache 管理

- 現有 `.cache` 統一改成 `workspace/hotdata/` 下的分層目錄

## 15.3 最終模組化後的結構

```text
fin/
├── docker/
│   ├── app.Dockerfile
│   ├── ui.Dockerfile
│   └── trainer.Dockerfile
├── compose/
│   ├── docker-compose.yml
│   ├── prometheus.yml
│   └── grafana/
├── config/
│   ├── settings.toml
│   ├── profiles/
│   └── prompts/
├── src/
│   ├── orchestration/
│   ├── data_ingest/
│   ├── canonical/
│   ├── features/
│   ├── signals/
│   ├── portfolio/
│   ├── reporting/
│   ├── storage/
│   ├── monitoring/
│   ├── registry/
│   └── ui/
├── scripts/
│   ├── windows/
│   └── linux/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   └── replay/
├── workspace/
│   ├── hotdata/
│   ├── runs/
│   ├── outputs/
│   ├── logs/
│   └── tmp/
└── docs/
```

---

## 十六、正式 artifact 契約

## 16.1 `signal.parquet`

必要欄位：

- `trade_date`
- `instrument`
- `score`
- `bar_freq`
- `model_id`
- `feature_set_version`
- `data_snapshot_id`

## 16.2 `today_position.csv`

必要欄位：

- `trade_date`
- `instrument`
- `target_weight`
- `notional`
- `score`
- `selection_reason`

## 16.3 `today_trades.json`

必要欄位：

- `trade_date`
- `instrument`
- `action`
- `delta_weight`
- `prev_weight`
- `new_weight`
- `reason`

## 16.4 `daily_report.json`

必要欄位：

- `market_summary`
- `position_change_summary`
- `factor_summary`
- `coverage_summary`
- `stability_summary`
- `risk_flags`
- `artifact_refs`
- `disclaimer`

## 16.5 `run_manifest.json`

必要欄位：

- `run_id`
- `trade_date`
- `mode`
- `data_snapshot_id`
- `feature_set_id`
- `model_id`
- `schema_version`
- `prompt_version`
- `git_commit`
- `started_at`
- `ended_at`
- `status`
- `artifact_uris`

---

## 十七、資料完整度與 retrain gate

## 17.1 coverage checker

每天計算：

- revenue count coverage
- revenue cap-weighted coverage
- financial count coverage
- financial cap-weighted coverage
- missing critical names

## 17.2 retrain decision

### 平日

- 只做 sync + signal + report
- 不重訓

### 月營收達標後

- 標記可做輕量 fine-tune / refresh

### 季報達標後

- 產生 candidate retrain
- 比較 champion vs candidate
- 勝出才 promotion

## 17.3 promotion 與 retrain 分離

- `retrain_decision.json`：是否值得訓練 candidate
- `promotion_decision.json`：是否讓 candidate 取代 champion

---

## 十八、未來 Qlib / LightGBM 升級路線

## 18.1 第一階段

保留現有 rule-based + LLM-assisted pipeline

## 18.2 第二階段

加入：

- canonical ETL
- feature namespaces (`tech_*`, `fund_*`, `nlp_*`)
- signal contract
- manifest

## 18.3 第三階段

加入：

- LightGBM baseline
- model registry metadata
- candidate / champion

## 18.4 第四階段

加入：

- SHAP
- drift monitoring
- retrain gate

## 18.5 第五階段

加入：

- Qlib dataset / handler / training workflow
- Optuna
- MLflow

也就是說：

> 先把 Windows Docker 版的 deterministic pipeline 做穩，再接真正的研究引擎。

---

## 十九、安全與 Secrets

### 19.1 secrets 存放

- `.env.local` 不進版控
- Windows Credential Manager 或 Docker secrets（若後續升級）
- LLM key / Supabase key / pCloud auth token 分開管理

### 19.2 不能做的事

- 把 API key 寫進 repo
- 把 WebDAV password 硬寫進腳本
- 用個人帳密當正式 pipeline 登入方式

### 19.3 LLM 使用原則

- LLM 只看結構化 artifacts
- LLM 只產生結構化報告
- 不讓 LLM 直接決策買賣
- 報告一定要保留 fallback 模板

---

## 二十、測試與驗收

## 20.1 測試層級

- `unit`
- `contract`
- `integration`
- `replay`
- `monitoring`

## 20.2 最低驗收門檻

### Pipeline

- 同日重跑 idempotent
- failure 可 resume
- manifest 必寫

### Data

- 無未來資料滲漏
- 必要欄位完整
- snapshot 可追溯

### Signal

- instrument 唯一
- weight sum = 1
- trade diff 正確

### Report

- schema valid
- 投資建議語氣

### Report

- schema valid
- 投資建議，

ex:

> **投資建議：買進，目標價：300 元，投資理由：基本面持續改善，營收／獲利成長明確，技術面站穩月線，趨勢偏多。賣出條件：股價跌破 250 元停損，基本面轉弱（營收連續兩季衰退），達到目標價 300 元分批獲利了結。**

- 有 artifact references
- 有 artifact references

### Monitoring

- Prometheus 抓到關鍵 metrics
- Grafana 至少有 3 個正式 dashboard

---

## 二十一、實作分階段計畫

## Phase 0：Windows Docker 基礎盤

目標：可穩定啟動本機 stack

交付：

- Docker Desktop + WSL2
- compose skeleton
- Streamlit + Prometheus + Grafana 起來
- workspace 路徑固定
- pCloud API token 可用

退出條件：

- UI 可開
- metrics 可看
- pCloud API smoke test 通過

## Phase 1：把現有 CLI 工具容器化

目標：現有系統可在 Docker one-shot 內跑

交付：

- `quant-sync`
- `quant-financials`
- `quant-daily`
- Task Scheduler 啟動成功

退出條件：

- 能每天自動跑一次
- log 與 outputs 存到 workspace
- 程式不依賴人工 cd / activate venv

## Phase 2：Artifact-first 重構

目標：正式輸出從 `DailyResult` 過渡到 artifact contracts

交付：

- `signal.parquet`
- `today_position.csv`
- `today_trades.json`
- `daily_report.json`
- `run_manifest.json`

退出條件：

- outputs 可 schema 驗證
- pCloud 上有正式版本化 artifacts

## Phase 3：Supabase 控制面接入

目標：UI 與 pipeline 狀態不再只靠本地檔案

交付：

- pipeline_runs / coverage / model_versions / report_index tables
- UI 改讀 DB
- Grafana 讀 PostgreSQL

退出條件：

- 最新狀態可從 DB 取回
- 即使重啟本機也能重建 dashboard 狀態

## Phase 4：Coverage checker 與 retrain gate

目標：把財報完整度檢查做成正式決策點

交付：

- coverage snapshots
- retrain_decision
- promotion policy

退出條件：

- 每日 coverage 可追蹤
- retrain 只在明確規則下觸發

## Phase 5：模型平台化

目標：導入 LightGBM / SHAP / MLflow / future Qlib

交付：

- trainer container
- registry metadata
- SHAP pipeline
- candidate vs champion promotion

退出條件：

- 有 baseline model
- 有可視化解釋
- 有可回滾 promotion

---

## 二十二、最終一句話

> **v7 的核心不是把系統搬上雲，而是把 Windows 電腦升級成「Docker 化的本地研究工作站」：Windows 管宿主與排程，WSL2/Linux 容器管執行，pCloud API 管冷資料，Supabase 管狀態，Streamlit 管操作，Grafana 管監控。**

這樣的結構最適合你現在的預算、硬體、與系統成熟度，也保留了未來升級成完整量化研究平台的路。
