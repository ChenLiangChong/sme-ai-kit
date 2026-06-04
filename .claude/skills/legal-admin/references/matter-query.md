# 案件查詢與管理（matter query）— 核心 loop 的步驟 4

> 觸發：「林先生的案子是哪件」「2026-民-014 進度」「王曉明還有什麼時限沒處理」「幫我開一個新案件」「這個書狀我送出去了」。
> 自然語言 → 直接查到案件、期限、行事曆。律師不用記案號。

## 查案件（人名 / 案號 / 當事人）

- `find_matter_by_party(party_name="林曉明")` —— 模糊比對委任人名字（也比對案由、案號），進行中（open）案件排前面。**律師最常用的入口**。
- `get_matter(matter_id)` —— 單一案件完整資訊（案由/法院/審級/主辦律師 + 該案所有時限摘要）。
- `list_matters(status="open")` —— 列進行中案件；可加 `lead_attorney` 篩主辦。

## 查時限

- `list_deadlines(matter_id=N)` —— 某案所有時限（含已遞交/逾期）。
- `list_upcoming_deadlines(within_days=14)` —— 跨案、按內部期限升冪、最急在前（每日彙整也用它，見 daily-digest）。
- `get_deadline(deadline_id)` —— 單筆完整資訊，含 **calc_trace 計算軌跡**（律師可逐步覆核引擎怎麼算出來的）＋ 逾期救濟備援 ＋ 教示比對 ＋ 行事曆同步狀態。**律師質疑日期算對不對時，給他看這個。**

## 建案件

`create_matter(title="○○請求給付貨款", matter_no="2026-民-014", client_name="林曉明", practice_area="civil", court="臺灣臺北地方法院", court_case_no="115年度訴字第XX號", stage="first_instance", lead_attorney="林律師", has_local_agent=1)`

- `matter_no` 唯一（撞號會擋、回既有案件 ID）。
- `practice_area`：civil/criminal/admin/family/ip/labor/non_litigation。
- `has_local_agent`：律所住法院所在地（在途歸零）常為 1；之後該案建時限 `has_local_agent=-1` 會沿用這個設定。
- 當事人只存 `client_name` 輕量欄位（**不做完整 CRM**，SPEC 決策）；要查得到名字就夠。

## 標記已遞交

書狀送出法院後 → `mark_deadline_filed(deadline_id, filed_by="林律師")` → 狀態轉 `filed`、**cron 不再提醒**。

> **重要**：實際送出去才標 filed。標了就停止倒數提醒，提早標＝失去保護。

## 失敗情境判讀

- **`find_matter_by_party` 找不到** → 可能還沒建案件，或名字記法不同（公司全名 vs 簡稱）。換關鍵字或 `list_matters` 翻、真的沒有就 `create_matter`。
- **`mark_deadline_filed` 回「目前狀態為『已遞交/已取消』、非待處理」** → 這筆已被標過（或取消）。`get_deadline` 看現況，不要當系統錯誤。
- **`get_matter` / `get_deadline` 在受限層對機密案件回「找不到案件/時限 #N」** → 這是刻意設計：受限層對機密案件回**與「不存在」完全相同**的泛化錯誤（anti-oracle、不洩漏機密案件存在），非真的查無。個人律所通常不分層（全權限看得到）；若真在受限層，這是預期阻擋（見 SKILL〈安全執行模型〉）。
