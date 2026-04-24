# Skill 翻譯排版規範

本文件定義 `.claude/skills/social-media/references/` 底下每個模組翻譯後應遵守的統一結構、排版與語氣。

搭配 [terminology.md](terminology.md) 使用。

---

## 一、每個模組的標準結構

所有模組依下列順序組織段落。若原檔沒有某段可略，但已有的段落順序不得調換。

```
# {模組標題}
{1-2 句開場：這個模組在做什麼、何時使用}

---

## {核心知識段 1}
## {核心知識段 2}
## {核心知識段 n}
   ↑ 原英文主體知識，翻譯為中文

---

## Proactive Triggers（主動觸發）
何時主動提出問題或警示，不等使用者問

## Output Artifacts（產出物）
| 使用者要什麼 | Claude 給什麼 |

## Communication（溝通原則）
回答格式、信心標註、結構

---

## Do's and Don'ts
### Do
- {短條目，行為規則}
### Don't
- {短條目，反例}

---

## 快速參考
### {流程名稱 1}
1. {步驟}
### {流程名稱 2}
1. {步驟}

---

## Related Skills
- **xxx.md** — {何時用 / 何時不用}
```

---

## 二、段落撰寫規則

### 開場
- 1-2 句，不超過 80 字
- 說明「這是什麼」+「什麼時候用它」
- 不要寫「You are an expert...」這種第二人稱 roleplay，改成「本模組負責 / 本模組提供」或直接描述功能

### 主體知識
- 知識類內容（表格、步驟、框架、模板）**翻譯為中文**
- 程式碼區塊、變數名稱、API 端點**保留英文**
- 定位聲明模板等「填空用」模板：依照標準雙語化規則，中文在前、英文關鍵字加括號並陳
  ```
  為 (For) [目標客戶]
  其 (Who) [需求陳述]
  該 (The) [產品] 屬於 (Is A) [品類]
  ```
- 人名、書名、公司名、方法論名**保留英文**（例：April Dunford、Sean Ellis test）

### 表格
- 欄位標題翻譯為中文
- 內容值中若含**行業通用縮寫或專有名詞**則保留英文（見 terminology.md 白名單）
- 範例欄位若是英文文案範例，**保留英文**（因為是示範 English copy）並在下一行加中文註解
- 欄寬若過長，可拆兩欄或用條列式

### Proactive Triggers
- 格式固定：`**{觸發情境}** → {Claude 應做的行為}`
- 翻譯為中文，但觸發條件若是系統事件（如 `query_knowledge returns empty`）保留英文

### Output Artifacts
- 表格欄位固定兩欄：「使用者要什麼」「Claude 給什麼」
- 不用「When you ask for... You get...」直譯

### Communication
- 固定包含四點：
  1. **先結論**（Bottom line first）
  2. **What + Why + How**
  3. **行動有負責人與期限**
  4. **信心標註** — 🟢 高信心 / 🟡 需測試 / 🔴 假設待驗證

### Do's and Don'ts
- 保留英文標題 `Do` / `Don't`（不改「該做 / 不該做」）
- 條目用中文，**每條 1 行、動詞開頭、40 字內**
- Don't 條目每條以「不要」開頭
- 數量：Do 4-6 條、Don't 4-6 條

### 快速參考
- 每個子流程 3-7 個步驟
- 步驟用數字編號，動詞開頭
- 不要重複主體知識的表格，只寫「操作順序」

### Related Skills
- 格式：`**{檔名.md}** — {一句話說明：何時用 / 何時不用}`
- **不要留下英文原句**如 `USE when...` / `NOT for...`
- 改寫為：「**email-outreach.md** — 用於 Email 序列與冷開發。不適合頁面主文案。」

---

## 三、語氣規則

| 對象 | 用語 | 舉例 |
|------|------|------|
| 對最終使用者（老闆、客戶） | 您 | 「建議您先完成定位再開始行銷投放」 |
| 對 Claude 的內部指令 | 自然中文，動詞開頭 | 「先載入品牌語氣，再撰寫文案」 |
| 敘述觀念 | 中立陳述 | 「定位是為什麼選你，不是你有什麼」 |

**不使用的語氣：**
- 過度口語（啦、耶、喔）— 除非是在「台灣市場」相關模組舉例消費者語氣
- 過度正式官腔（茲、謹、特此）
- 命令老師式口吻（你必須、你應該、切記）— 改成中立陳述

**允許使用的風格詞：**
- 「建議」「請」「先」「再」「才能」「避免」「確認」
- Emoji：只在信心標註（🟢🟡🔴）和少數強調處使用，**不在內文濫用**

---

## 四、程式碼與命令

- 程式碼、命令、變數名稱、檔名、路徑**一律保留英文**
- 命令範例的註解可翻中文：
  ```python
  query_knowledge(category='brand')  # 查詢品牌相關規則
  ```
- 環境變數、API 名稱、函式名稱**不翻譯**

---

## 五、連結與交叉引用

- 內部檔案連結：`[copy-editing.md](copy-editing.md)`，描述用中文
- 外部連結：保留原文標題，括號註中文
- 跨模組引用：用 terminology.md 的譯名，不要自己另譯

---

## 六、不動的段落

下列段落若原檔已存在且為**台灣在地化內容**，**保留原樣不重寫**：

- `台灣中文文案注意事項`（copywriting.md）
- `台灣繁簡差異表`（各處）
- `CTA 用語對照表`（台灣常用中文 CTA）
- `節慶文案注意事項`
- `法規紅線`
- `taiwan-market.md` 全檔
- `line-marketing.md` 大部分內容

若有需要微調，只修用詞不動結構。

---

## 七、翻譯前後檢核清單

翻譯完一個檔後，請逐項檢查：

- [ ] 所有主體段落都已翻為中文（除保留原文白名單）
- [ ] 術語完全對照 terminology.md，無自創譯名
- [ ] 無簡中用字（「视频 / 软件 / 项目 / 博客 / 点赞」等）
- [ ] 段落順序符合標準結構
- [ ] Do / Don't 每條 40 字內、動詞開頭
- [ ] 快速參考每個子流程 3-7 步
- [ ] Related Skills 全中文描述，無殘留 `USE` / `NOT for` 英文
- [ ] 程式碼 / 命令 / 變數保留英文
- [ ] 對使用者用「您」，對 Claude 用自然動詞
- [ ] Emoji 僅用於信心標註
- [ ] 無殘留英文段落（除保留原文白名單）

---

## 九、雙語模板規則（v2 新增）

skill 裡的英文模板／label／術語依「目的」分三級處理：

### 第 1 級：保留純英文（不動）

技術標準、程式碼、API、data schema、工具名稱、網路識別符號：
- 函式呼叫：`query_knowledge(category='brand')`、`record_transaction(...)`
- Event 名稱：`signup_completed`、`page_view`
- UTM 參數：`utm_source=facebook&utm_medium=cpc`
- 縮寫（見 terminology.md 白名單）：TAM、SAM、SOM、ICP、ROI、CTA、MQL...
- 品牌與產品名：Salesforce、Gong、HubSpot、Claude、Anthropic
- 方法論原文名：April Dunford、Sean Ellis test、Pratfall Effect（但**首次出現要加中文註解**，見第 3 級）

### 第 2 級：中英並陳（中文在前、英文括號）

**填空模板的 label**、**文化專有名詞首次出現**、**方法論步驟專有名詞**：

#### 模板 label 格式
```
競品 (Competitor)：[名稱]
概況 (Overview)：創立 [年份]，融資 [階段]
殺手提問 (Land Mines — 提前埋下的問題)：
```

**規則：**
- 中文在前、英文在括號（反向會讓讀者認知錯亂）
- 英文用**半形括號** `(  )`，不用全形 `（ ）`——在 code block 中保持 monospace 乾淨
- 英文用 Title Case（如 `(Land Mines)`、`(Competitor)`）而非全大寫（避免視覺噪音）；若原始術語本身是全大寫縮寫（如 `SAM`、`TAM`）則保留原樣
- 若英文詞需要解釋意圖，括號內加破折號 `—`：`(Land Mines — 提前埋下的問題)`

#### 方法論專有名詞首次出現
```
April Dunford（品牌定位大師）提出七步法...
Sean Ellis test（必要性測試，40% 法則）
```

### 第 3 級：全中文化（占位符、描述、中性商業詞）

模板內的**占位符（placeholder）**、**描述性文字**、**中性商業詞**全面中文：

- ❌ `OVERVIEW: Founded [year], Funding [stage], Size [employees]`
- ✅ `概況 (OVERVIEW)：創立 [年份]，融資 [階段]，規模 [員工數]`

- ❌ `"[Their claim]"` / `"[Your assessment]"`
- ✅ `「[對方的宣稱]」` / `「[您親自評估後的觀察]」`

- ❌ `LAST UPDATED: [Date]`
- ✅ `最後更新 (LAST UPDATED)：[日期]`

中性商業詞翻譯對照（摘自 terminology.md）：
- Overview → 概況
- Positioning → 定位
- Target Customer → 目標客戶
- Strengths / Weaknesses → 優勢 / 劣勢
- Our Advantages → 我方優勢
- When We Win / Lose → 勝出情境 / 敗退情境
- Talk Track → 應對話術
- Recent Changes → 近期變化
- Last Updated → 最後更新

### 判斷樹（遇到英文先問自己）

```
是技術標準 / 程式碼 / 函式 / 品牌原名嗎？
├─ 是 → 第 1 級，保留英文
└─ 否 → 是模板 label 或方法論專有名詞嗎？
         ├─ 是 → 第 2 級，中文(英文) 並陳
         └─ 否 → 第 3 級，全中文
```

### 特殊保留項

**April Dunford 定位聲明模板**——適用標準雙語化規則（中文在前、英文關鍵字加括號並陳，保留方法論辨識度同時降低英文閱讀成本）：
```
為 (For) [目標客戶]
其 (Who) [需求陳述]
該 (The) [產品] 屬於 (Is A) [品類]
提供 (That) [關鍵利益]
相較於 (Unlike) [競爭替代方案]
我方產品 (Our Product) [核心差異]
```
（不再是例外規則——與整份 style-guide 的 L2 雙語化規則一致）

---

## 八、交付格式（重要）

**絕對不要直接覆蓋原檔。**

流程：
1. 翻譯後的中文版寫到 `docs/skill-translation/drafts/<原檔名>.md`
   - 例：`docs/skill-translation/drafts/pmm-positioning.md`
   - 檔名**保持與原檔相同**，路徑不同即可對照
2. 全部 22 檔翻完後，`.claude/skills/social-media/references/` 是英文原版、`docs/skill-translation/drafts/` 是中文版——同時存在（44 份）
3. 使用者逐檔對照校對，通過後才由使用者授權覆蓋原檔
4. 覆蓋後才砍 drafts/ 底下的對應檔

**禁止：**
- 直接覆蓋 `.claude/skills/` 底下任何檔
- 在原檔底部附加中文版雙語並存
- 建立 `.zh.md` 雙檔名（會破壞 Claude skill 載入）
