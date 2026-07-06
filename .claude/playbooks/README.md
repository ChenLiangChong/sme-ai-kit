# playbooks/ — 開發 session 制度層（legal-admin）

> 這個目錄是給「在本 repo 做開發」的 Claude session 讀的制度檔（2026-07-06 由高階模型立制）。
> 與產品行為無關：產品行為契約在 root `CLAUDE.md`、業務流程在 `.claude/skills/`。
> dev session 開場 hook 會指到這裡；**開工前至少讀完本 README + `10-model-dispatch.md` 的 §0 與 §7**。

## 檔案索引（編號 = 建議閱讀順序）

| 檔案 | 一句話 | 什麼時候讀 |
|------|--------|-----------|
| `00-diagnosis.md` | 本環境三大漏洞（角色混線 / context 浪費 / 驗證自驗）與修法——其餘檔案的「為什麼」 | 第一次進場、或懷疑規則背後理由時 |
| `10-model-dispatch.md` | 模型調度守則：指揮官不下場、派工三件套、升降級路徑、codex 規約、環境 gotchas | **每個 session 開工前**（至少 §0、§7） |
| `20-judgment-rubrics.md` | 判斷 rubric：何時升級 / 何時算完成 / 何時問使用者 / 方向錯了的訊號 / 品質底線，每條附正反例 | 要宣稱完成前、卡住時、想重試第三次前 |
| `30-delegation-templates.md` | 派工 prompt 模板：搜尋 / 實作 / 重構 / 研究 / 審查，含驗收條件與回報格式填空 | 每次派 subagent / codex 前照抄填空 |
| `40-maintenance.md` | 維護協議：哪些檔可自行改、哪些先問、教訓寫回哪裡、多長要精簡 | 想改制度檔時、踩坑後 |
| `90-letter.md` | 給未來 session 的信：沒被問但最重要的三件事 + 這套制度的退化模式與預防 | 第一次進場、或發現制度「怪怪的」時 |

## 三條不看檔也要記得的鐵則

1. **指揮官不下場**：大量讀取 / 掃 repo / 網查 / 批次改檔 → 派 subagent；主對話只進結論與 `檔:行`。
2. **驗證不自驗**：宣稱完成前，證據必須是測試輸出 / fresh-agent read-back / codex 確認之一——「我看碼覺得對」不算。
3. **兩條產品線永不合流**：master（通用 SME）⊥ legal-admin（律所）；通用改進要過去只能 copy / cherry-pick，永不 merge。
