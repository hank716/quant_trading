# Windows Task Scheduler 排程設定

## 前置條件

1. Docker Desktop 已啟動並設定為開機自動啟動
2. `compose/docker-compose.yml` 正確設定
3. `.env.local` 已建立於專案根目錄

## 新增排程工作

### 開啟 Task Scheduler

1. 按 `Win + R`，輸入 `taskschd.msc`
2. 點選「建立基本工作」

### 每日資料同步（quant-sync）

| 欄位 | 值 |
|------|----|
| 名稱 | fin-quant-sync |
| 觸發器 | 每日，08:00 |
| 動作 | 啟動程式 |
| 程式 | `powershell.exe` |
| 引數 | `-NonInteractive -File "C:\path\to\fin\scripts\windows\run_sync.ps1"` |
| 起始於 | `C:\path\to\fin` |

### 每日主程式（quant-daily）

| 欄位 | 值 |
|------|----|
| 名稱 | fin-quant-daily |
| 觸發器 | 每日，14:30（收盤後） |
| 程式 | `powershell.exe` |
| 引數 | `-NonInteractive -File "C:\path\to\fin\scripts\windows\run_daily.ps1"` |

### 財報慢同步（quant-financials）

| 欄位 | 值 |
|------|----|
| 名稱 | fin-quant-financials |
| 觸發器 | 每週日，06:00 |
| 程式 | `powershell.exe` |
| 引數 | `-NonInteractive -File "C:\path\to\fin\scripts\windows\run_financials.ps1"` |

## 注意事項

- 勾選「使用最高權限執行」以確保 Docker 指令可執行
- 「不管使用者是否登入都執行」需設定服務帳號密碼
- 可在工作「歷程記錄」頁確認每次執行結果
