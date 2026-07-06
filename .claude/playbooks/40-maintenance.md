# 40 — 維護協議（未來的 session 怎麼安全地更新這套制度）

> 讀者：未來在本 repo 開發的每個 session。原則：**制度檔可以演化，但演化要留痕、要可回退、不能自我膨脹。**

## §1 權限分級（改之前先查這張表）

| 對象 | 權限 | 條件 |
|------|------|------|
| `playbooks/` 各檔的「教訓登記簿」段 | **自行追加** | 按 §3 格式，一坑一行 |
| `playbooks/` 正文（規則本體） | **自行修正錯誤**（路徑失效、工具名變了、與現實不符）；**新增/刪除規則先問使用者** | 修正要在 commit message 說明「原文錯在哪、證據」 |
| `00-diagnosis.md` 的診斷項 | 過時就標記 `【已過時 YYYY-MM-DD：原因】`，**不刪**（歷史是後人理解規則的證據） | — |
| root `CLAUDE.md` / `AGENTS.md` | **行為契約段動之前必問使用者**；錯字/失效路徑修正可自主 | 它同時是產品規格；改 CLAUDE.md 即可、AGENTS.md 由 pre-commit hook 同步 |
| `.claude/settings.json`、`.claude/hooks/*` | **動之前必問使用者**（影響所有 session 的注入行為） | 改 `session-mode.py` 後必跑檔頭的自測指令 |
| `.claude/skills/**` | 觸發描述（SKILL.md 的何時載入）動之前必問（牽動觸發 eval）；reference 內容按 root〈文件權威層級〉 | — |
| memory（`~/.claude/projects/.../memory/`） | 照 memory 系統自身規則 | 跨 session 事實放這裡、不放 playbooks |

## §2 改檔前的固定動作

1. 備份：`mkdir -p _backup/$(date +%F) && cp {檔} _backup/$(date +%F)/{檔名}.bak`（`_backup/` 已列 `.gitignore`、不進 git）。
2. 改完 read-back：新舊 diff 看一眼，確認只改了想改的。
3. 若改的是規則本體：grep 其他 playbook + CLAUDE.md 有沒有引用舊規則（避免改一處、留三處矛盾）。

## §3 教訓寫回哪裡、什麼格式

**判斷樹**：
- 這個坑是「派工/模型調度」的 → `10-model-dispatch.md` 末尾登記簿
- 是「判斷失誤」（假完成、方向錯、該問沒問）→ `20-judgment-rubrics.md` 末尾登記簿
- 是「環境事實」（工具行為、路徑、指令）→ `10-model-dispatch.md` §7 gotcha 表加一列
- 是「跨 repo / 跨 session 的專案事實」→ memory 系統（不放 playbooks）
- 是「產品行為」→ 不屬於制度層,走 root〈文件權威層級〉進 CLAUDE.md 或 skill

**格式（一坑一行）**：
```
- YYYY-MM-DD｜一句話教訓（做什麼會踩）｜證據：commit/檔:行/事件
```
**反例**：寫成散文段落、寫感想（「要更小心」）、或把同一坑寫進三個檔。

## §4 精簡門檻（防制度自我膨脹）

- 單一 playbook **超過 250 行** → 該 session 順手做一次精簡：登記簿裡已被吸收進正文的條目刪掉、重複規則合併。
- 登記簿 **超過 15 條** → 把高頻坑上升為正文規則（一條正文換掉多條登記）、其餘保留。
- 精簡也是「改正文」：走 §1/§2 的規則（備份、diff、grep 引用）。
- **不准的膨脹方式**：為單一事件加一條永久規則（先進登記簿觀察，重複發生才升正文）；複製 CLAUDE.md 內容進 playbooks（引用就好）。

## §5 制度健康檢查（低頻，發現異常才做）

懷疑制度失效時（例如 dev session 又開始跑營運 readout）：
1. `python3 .claude/hooks/session-mode.py session-start` 自測 hook 還活著、輸出正確。
2. `ls .claude/playbooks/` 7 檔俱在（README + 00/10/20/30/40/90）；`grep -c "登記簿" .claude/playbooks/10-model-dispatch.md` 抽查未被清空（≥1 才正常）。
3. 抽一條規則裡的路徑實查存在（今天的例子:worktree 改名 `sme-ai-kit-wave1`→`sme-ai-kit-lawyer`,所有寫死路徑的規則都要跟著改——寫規則時能用相對路徑就用相對路徑）。

## 教訓登記簿（本檔自身的）

- 2026-07-07｜worktree 改名會讓 playbooks 裡寫死的絕對路徑全數失效；新規則能寫相對路徑就寫相對路徑｜證據：`git worktree move` wave1→lawyer 後 grep 修正 2 處
- 2026-07-07｜多 agent 協作下「已核准的行動」會在 refined 裁示到達前落地＝交錯雙寫；大動作核准必須附「執行者鎖定」宣告、執行腳本必 assert 前置狀態（恰一列命中才動）｜證據：Windows e2e #2 清洗與 #5 還原兩度交錯、幸皆冪等收場
