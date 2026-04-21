# Claude Code 啟動指南

> 一步步教你怎麼讓 Claude Code 接手這個專案。第一次設定大約 15 分鐘。

---

## 前置準備（只做一次）

### 1. 確認 Claude Code 已安裝

```bash
claude --version
```

如果沒有：

```bash
npm install -g @anthropic-ai/claude-code
```

### 2. 安裝 GitHub CLI（自動 merge 需要）

**Windows（PowerShell 管理員）：**
```powershell
winget install --id GitHub.cli
```

**WSL / Linux：**
```bash
sudo apt install gh  # Ubuntu/Debian
# 或
brew install gh      # macOS
```

### 3. GitHub CLI 登入

```bash
gh auth login
```

選擇：
- GitHub.com
- HTTPS
- Login with a web browser
- 貼一次性代碼

確認登入成功：
```bash
gh auth status
```

### 4. 設定 Git 身分（如果還沒）

```bash
git config --global user.name "你的名字"
git config --global user.email "你的 GitHub email"
```

### 5. 建立 `.env.local`

在 repo 根目錄建立：

```bash
cd /path/to/fin  # 你的 repo 路徑
cp .env.example .env.local  # 若 .env.example 存在
# 或手動建立空的
touch .env.local
```

**先不用填 credentials**，Phase 0 和 1 用 mock mode。之後 Phase 2 再填 pCloud，Phase 3 再填 Supabase。

---

## 第一次啟動 Claude Code

### Step 1：進到 repo 目錄

```bash
cd /path/to/fin
```

### Step 2：把 TASKS.md 放到 repo 根目錄

把我給你的 `TASKS.md` 複製到 repo 根目錄：

```bash
cp ~/Downloads/TASKS.md ./TASKS.md
git add TASKS.md
git commit -m "chore: add TASKS.md for Claude Code autonomous execution"
git push
```

### Step 3：啟動 Claude Code

```bash
claude
```

第一次啟動會讓你登入（用 claude.ai 帳號）。

### Step 4：給它第一個指令

在 Claude Code 提示字元裡輸入：

```
看 TASKS.md 和 git log，從 Phase -1 開始做起
```

它會：
1. 讀 TASKS.md
2. 讀 git 狀態
3. 開始執行 Phase -1 的子任務
4. 每完成一個就 commit
5. Phase 完成後建 PR 並自動 merge 到 develop

### Step 5：離開並讓它持續工作

當 rate limit 快到時，你可以：
- 按 `Ctrl+C` 中斷
- 或讓它自己停（rate limit 到了會停）

---

## 後續啟動（每次只要這兩行）

```bash
cd /path/to/fin && claude
```

然後輸入：

```
看 TASKS.md 和 git log，繼續下一個未完成的任務
```

它會：
1. `git status` 和 `git log` 看現在的狀態
2. 找到 TASKS.md 第一個 `[ ]`
3. 繼續做

---

## 你需要做的事（minimal）

### 每天（約 5 分鐘）

1. 打開 GitHub 看有沒有新的 PR 合併到 develop
2. 瀏覽一下 commit history，確認方向沒偏
3. 如果 repo 根目錄出現 `BLOCKED.md`，看它需要什麼（通常是 credentials）

### 定期（約 30 分鐘）

當 `develop` 累積了幾個 Phase，你決定要不要合併到 `main`：

```bash
gh pr create --base main --head develop --title "Release: Phase 0-2 complete"
# 自己 review、自己 merge
```

---

## 常見狀況

### 狀況 1：Claude Code 卡住了

它會在 `BLOCKED.md` 寫清楚卡在哪。打開看就知道要提供什麼。

最常見的是：
- pCloud token（Phase 2 之後需要）
- Supabase URL/key（Phase 3 之後需要）

提供後告訴它：
```
credentials 已加到 .env.local，繼續 TASKS.md
```

### 狀況 2：PR 被 auto-merge 失敗

通常是 GitHub branch protection 擋住。你可以：
- 手動 merge
- 或暫時關閉 develop 的保護規則（不建議關 main 的）

### 狀況 3：測試 fail

Claude Code 會自己嘗試修，如果修不好它會在 `BLOCKED.md` 紀錄然後跳過。你可以看 commit history 找到是哪個子任務，手動介入。

### 狀況 4：Rate limit 到了

`Ctrl+C` 離開，5 小時後再啟動。**工作進度不會遺失**，因為全部都在 git 裡。

---

## 建議的工作節奏

| 時段 | 你要做什麼 |
|------|-----------|
| 早上 | 啟動 Claude Code，輸入繼續指令，離開 |
| 中午 | 看一眼 GitHub，review PR |
| 傍晚 | 重啟 Claude Code（rate limit 已重置） |
| 晚上 | 再看一眼進度 |

這樣一天可以推進 2-3 個 Phase 的子任務，不用你動手寫程式。

---

## 安全檢查

在讓 Claude Code 自由運作前，確認以下：

- [ ] GitHub repo 的 `main` 分支有設 branch protection（禁止直接 push）
- [ ] `.env.local` 在 `.gitignore` 裡（確認不會被 commit）
- [ ] 已執行 `gh auth status` 確認登入
- [ ] 已啟動 `claude` 並登入成功
- [ ] 第一次手動 review 一兩個 Phase 再完全放手

---

## 進階：設定 GitHub branch protection

到 GitHub repo → Settings → Branches → Add rule：

**針對 `main`：**
- ✅ Require a pull request before merging
- ✅ Require approvals (1)
- ✅ Do not allow bypassing

**針對 `develop`（可選）：**
- ✅ Require status checks to pass（如果有 CI）
- 其他都不勾，讓 Claude Code 可以自動 merge

這樣 Claude Code 絕對碰不到 `main`，只能在 `develop` 和 `feat/*` 工作。
