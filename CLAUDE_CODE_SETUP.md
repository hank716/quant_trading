# Claude Code 啟動指南

## 前置條件（只做一次）

```bash
# 確認 Claude Code 已安裝
claude --version
# 若無：npm install -g @anthropic-ai/claude-code

# GitHub CLI 登入（自動 merge 需要）
gh auth login
gh auth status

# Git 身分設定（若還沒）
git config --global user.name "你的名字"
git config --global user.email "你的 GitHub email"

# 建立本機環境變數檔
cp env.example .env.local
```

## 每次啟動

```bash
cd /path/to/fin
claude
```

然後輸入：

```
看 TASKS.md 和 git log，繼續下一個未完成的任務
```

Claude Code 會自動：
1. 讀 git 狀態與 TASKS.md
2. 找到第一個 `[ ]` 未完成子任務
3. 實作、測試、commit
4. Phase 完成後建 PR → develop 並 squash merge

## Agents 說明

本專案在 `.claude/agents/` 配置了 4 個專屬 agent，Claude Code 會根據任務類型自動選用：

| Agent | 負責 |
|-------|------|
| `fin-pipeline-engineer` | Phase 實作、Docker、Supabase、git workflow |
| `fin-test-engineer` | 單元測試、contract test、integration test |
| `taiwan-quant-analyst` | 訊號設計、策略評估、台股市場分析 |
| `fin-architect-doc` | 架構設計、ADR、文件維護 |

你也可以明確指定：

```
用 fin-architect-doc 幫 Phase 4 的 coverage checker 寫 ADR
```

## 你需要做的事

**每天（約 5 分鐘）：**
1. 看 GitHub 有沒有新的 PR 合併到 develop
2. 若 repo 根目錄出現 `BLOCKED.md`，提供它需要的 credentials

**需要 credentials 的 Phase：**
- Phase 2+：`PCLOUD_TOKEN`（填到 `.env.local`）
- Phase 3+：`SUPABASE_URL` + `SUPABASE_SERVICE_KEY`（見 [`docs/supabase-setup.md`](docs/supabase-setup.md)）

**提供 credentials 後告訴 Claude Code：**
```
credentials 已加到 .env.local，繼續 TASKS.md
```

## 常見狀況

| 狀況 | 處理 |
|------|------|
| 卡住了 | 看 `BLOCKED.md` 說明，提供所需資源 |
| Rate limit | Ctrl+C，5 小時後重啟，進度在 git 裡 |
| 測試 fail | Claude Code 會自修，修不好就寫進 BLOCKED.md |
| PR merge 失敗 | 手動 merge，或檢查 branch protection 設定 |

## Branch Protection 建議

GitHub repo → Settings → Branches：

**`main`：** Require PR + Require approval (1) + Do not allow bypassing  
**`develop`：** 不限制（讓 Claude Code 可自動 merge feature branch）
