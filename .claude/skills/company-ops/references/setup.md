# 環境設定指南（律所首次上線）

## 觸發情境

**系統導入**：首次開啟 Claude 時，`.mcp.json` 裡沒有 `line` server，或 LINE 工具無法使用。

> **本檔定位**：律所首次上線的環境 bootstrap——接 LINE token、寫 `.mcp.json`、`curl` 驗 webhook、（選配）Claude Desktop。內容 90% 與領域無關，只是把 OA 框成**所內單一官方帳號（所內專用、無對外客戶／行銷通道）**。**部門安全層（floor）分層是多人版才需要的升級路、個人律所不設 `SME_FLOOR`**（見第五節）。

---

## 一、LINE Channel 設定（所內單一 OA）

律所只跑**一個所內 LINE 官方帳號**：律師、助理、行政在自己手機上把判決書／裁定／開庭通知拍照或 PDF 丟進這個 OA，系統算時限、建案件、回彙整。**這個 OA 是對內工作通道、不對委任人或外部開放**（陌生人路由、對外行銷不在本產品範圍——見 `docs/legal/SPEC.md`）。

### 前提

顧問已事先完成：
- ngrok 帳號註冊 + 固定域名
- LINE Developers Console 建立 Messaging API Channel
- LINE Official Account 開通（**設為所內使用、不公開推廣加好友**）

### Step 1：收集密鑰

問使用者以下資訊：

| 需要什麼 | 哪裡拿 |
|---------|--------|
| LINE Channel Access Token | LINE Developers Console → Channel → Messaging API → Issue |
| LINE Channel Secret | LINE Developers Console → Channel → Basic settings |
| ngrok Authtoken | ngrok Dashboard → Your Authtoken |
| ngrok 固定域名 | ngrok Dashboard → Domains（例：xxx-yyy.ngrok-free.dev）|

### Step 2：設定 ngrok

```bash
ngrok config add-authtoken <authtoken>
```

用 Bash tool 執行。

### Step 3：更新 .mcp.json

讀取現有 `.mcp.json`，加入 `line` server：

```json
{
  "mcpServers": {
    "business-db": { ... },
    "line": {
      "type": "channel",
      "command": "<bun 的絕對路徑>",
      "args": ["run", "<專案路徑>/mcp-servers/line-channel/server.ts"],
      "env": {
        "CHANNEL_ACCESS_TOKEN": "<token>",
        "CHANNEL_SECRET": "<secret>",
        "LINE_CHANNEL_PORT": "8789",
        "SME_DB_PATH": "<專案路徑>/data/business.db",
        "NGROK_DOMAIN": "<域名>"
      }
    }
  }
}
```

用 `which bun` 取得 bun 路徑。專案路徑從現有 .mcp.json 的 business-db args 推算。

### Step 4：提示重啟

告訴使用者：

> LINE 設定完成！請輸入 `/exit` 退出，然後重新執行 `claude` 讓 LINE Channel 生效。

---

## 二、驗證（重啟後）

重啟後自動執行：

1. **business-db**：`get_context_summary(scope='full')` — 如果能跑就代表連線正常
2. **line channel**：嘗試 `list_channels()` — 如果能跑就代表 LINE MCP 正常
3. **ngrok**：用 Bash tool 執行 `curl -s https://<域名>/webhook` — 應回傳 404（代表 server 在跑但路徑不對，POST 才會處理）
4. **LINE webhook**：LINE Channel server 啟動時會自動設定 webhook URL

驗證通過後，從所長手機對這個 OA 丟一句話（或一張裁定照片）做端到端確認：所內 session 應收到 `<channel source="line">` 訊息並有結局。

### 驗證失敗處理

| 症狀 | 可能原因 | 修法 |
|------|---------|------|
| business-db tools 無法呼叫 | .mcp.json 路徑錯 | 檢查 python3 和 server.py 路徑 |
| line tools 無法呼叫 | token/secret 錯或 bun 路徑錯 | 重新檢查 .mcp.json 的 line 區塊 |
| ngrok curl 失敗 | ngrok 沒啟動或域名錯 | 檢查 NGROK_DOMAIN 和 authtoken |
| LINE 收不到訊息 | webhook URL 沒設好 | 到 LINE Console 手動確認 webhook URL |

---

## 三、Claude Desktop 設定（選配）

如果所長也要用 Claude Desktop / Cowork 直接查資料庫（不收發 LINE）：

### macOS

讀取 `~/Library/Application Support/Claude/claude_desktop_config.json`，加入 business-db：

```json
{
  "mcpServers": {
    "sme-business-db": {
      "command": "<python3 路徑>",
      "args": ["<server.py 路徑>"],
      "env": { "SME_DB_PATH": "<db 路徑>" }
    }
  }
}
```

### Windows (WSL)

找 `/mnt/c/Users/*/AppData/Roaming/Claude/claude_desktop_config.json`，用 WSL wrapper：

```json
{
  "mcpServers": {
    "sme-business-db": {
      "command": "wsl",
      "args": ["bash", "-c", "export SME_DB_PATH='<db路徑>' && <python3路徑> <server.py路徑>"]
    }
  }
}
```

設定完提示重啟 Claude Desktop。

---

## 四、注意事項

- LINE Channel 的 `type: "channel"` 只有 Claude Code 支援，Claude Desktop 不支援
- Claude Desktop 只能用 business-db（查 DB），不能收發 LINE
- 密鑰存在 .mcp.json 裡（已 .gitignore），不要手動上傳到任何地方
- ngrok 免費帳號每月有流量限制，所內單一 OA 的訊息量正常使用足夠

---

## 五、部門安全層（floor）部署 ——【多人版才需要，個人律所不設】

> **個人律所（單一律師、全權限單人）不需要這一節。** 依 `docs/legal/SPEC.md`：個人律所**不設 `SME_FLOOR`**（全權限單人、看全部、所有工具都在），`floor` / `confidential` 機制**保留為 inert 的升級路**——將來增聘助理 / 行政、要把財務或機密知識對部分人收斂時再啟用。下面講的是「多人版要分層時怎麼起、要準備哪些檔」；**機制本身（floor 兩道牆的把關演算法、`SME_FLOOR` 三態語義）一字不改、見 CLAUDE.md〈部門安全層（floor）與兩道牆〉，不在此重述。**

LINE-runtime 可以「分層」啟動：不同部門的 session 套不同的可信邊界，限制各層只看得到該看的資料、各層的 DB 工具白名單也不同。

### Step 1：用 start-line.sh `<層>` 受限啟動

`start-line.sh` 是 LINE-runtime 的啟動入口，帶一個 layer 參數決定這個 session 屬於哪一層：

```bash
./start-line.sh                # 不帶層 = 全權限（floor = data/、settings = .claude/line-runtime-settings.json）
./start-line.sh general        # 一般部門層（floor = data/general、settings = .claude/line-runtime-general.json）
./start-line.sh <層名>         # 任一已建好資料夾 + settings 的層
```

`start-line.sh <層>` 啟動受限層時會：注入 `SME_FLOOR=<層>`（business-db 據此套該層工具白名單＝第二道牆）、把 `cwd` 設成該層資料夾、載入該層 sandbox settings `.claude/line-runtime-<層>.json`（第一道牆）、並以 `--tools` built-in 白名單啟動；不帶層 ＝ `SME_FLOOR` 空 ＝ 全權限。**兩道牆 / 三態 / 工具白名單 / denyRead 清單的機制細節見 CLAUDE.md〈部門安全層（floor）與兩道牆〉——這裡只管部署要對齊什麼：**

起層前的前置條件（腳本會檢查、缺就 fail）：該層的資料夾 `data/<層>/` 要存在、該層 settings `.claude/line-runtime-<層>.json` 要存在。**這兩個都要對齊 floor-map（見 Step 2）裡的層名。**

`start-line.sh` 已在 repo（`base` 自動推導腳本所在的 repo root、不寫死絕對路徑 → 換機器 / 換資料夾 / 上 NAS 都免改）。各層 sandbox settings 用 **`.claude/line-runtime.example.json`** 當範本：每層複製一份成 `.claude/line-runtime-<層>.json`，把 `__REPO__` 換成 repo 絕對路徑、`<層>` 換成層名、`denyRead` 裡的 `<其他層N>` 補齊「除本層外所有層」的資料夾（漏列＝該層牆破洞）。**這個逐層手抄 + denyRead 交叉表正是 #13 manifest 生成器要自動化的；生成器上線前先照範本手建，上線後從 `floor-map.json` 自動產出（見 `docs/deployment/floor-nas.md`）。**

> **系統依賴：Linux 需裝 `bubblewrap`（`bwrap`）**——它是 Claude Code 在 Linux 的 sandbox 後端，floored 層 settings 設了 `sandbox.enabled` + `failIfUnavailable:true`，**缺 `bwrap` 受限層 session 會 fail-closed 起不來**。`install.sh` 會自動裝（`apt install bubblewrap`）；若 floored 啟動失敗先 `command -v bwrap` 檢查。macOS 用內建 `sandbox-exec`、不需此套件。`start-line.sh` 本身是 expect 腳本，另需 `expect`（install.sh 也會裝）。

> **不要在這裡寫死具體層清單**（如機密 / 內勤 / 對外）。哪些層、各層看哪些財務 / 機密知識，是多人版導入時所長拍板的客製設定，用 Step 2 的範例檔當起點即可。

### Step 2：floor-map.json ＝ 能力設定層

各層「能看哪些財務 / 是什麼角色 / 上報給誰」不寫死在腳本，而是集中在一張能力設定表。範例檔在 `mcp-servers/business-db/floor-map.example.json`，多人版導入時**複製成 `data/floor-map.json` 並改成這家律所的實際分層**：

```bash
cp mcp-servers/business-db/floor-map.example.json data/floor-map.json
# 再依所長拍板的分層結構改 floors 內容
```

每層可設的欄位（語義以範例檔 `_fields` 為準）：

| 欄位 | 作用 |
|------|------|
| `financial_visibility` | `none`（看不到財務、預設）/ `all`（看全部財務）/ `own_bu`（待 #11；目前 fail-closed 等同 none）。決定這層的 MCP 進程**有沒有財務工具** |
| `role` | `boss` / `manager` / `staff`，給上報與 HITL 判斷用 |
| `escalation_target` | 上報給誰：填 LINE user_id＝系統特判直送；其餘值（如 `'boss'`）走 `role=boss` → `admin` → `company.boss_line_id` 的 coalesce。（**目前未實作「填 floor 名」當收件人**）|
| `business_units` | 此層可碰哪些事業體（待 #11 BU-scoping 才真正生效；**個人律所為單一所、此欄留空 inert**）|
| `department` | 人看的部門標籤 |

無 `data/floor-map.json` 時系統走安全預設（全權限層看全部、其餘 `financial_visibility=none` / `role=staff` / 上報 `boss`），等同未啟用分層、向後相容——**個人律所就是這個狀態**。`floor-map.json` 屬機密設定、應在各受限層 settings 的 `denyRead` 內（範例 settings 已含）。

> floor-map 的欄位是**領域無關的通用能力設定**：`financial_visibility` 控的是會計類工具的去留，律所本身**不做記帳 / 收費 / 信託帳**（不在本產品範圍——見 `docs/legal/SPEC.md`），所以個人律所此欄維持預設、不啟用。多人版啟用分層後的兩 session 拓樸與身份路由、各層上報如何收斂，見 **line-comms.md〈執行模型：核准後一條龍〉**。

### Step 3：必須常駐一個全權限 session

分層部署時（多人版），**必須常駐一個 `SME_FLOOR=confidential` 的 session**（`./start-line.sh confidential`）。注意：bare `./start-line.sh`（`SME_FLOOR` 空）雖然工具上也是全權限，但所長 / admin 的 LINE 訊息被 line-channel **硬路由到 `confidential` 層**（`server.ts` 的 `BOSS_TARGET_FLOOR='confidential'`、待 #13 改由 floor-map 推導）——只有 `confidential` session 收得到、才接得住核准閉環。理由：

- 所長 / admin 的 LINE 訊息（含「核准 #N」）會被路由進全權限 session；沒有這層，所長的核准訊息**無處落地**、in-session push 的「核准 → 執行 → 回覆」閉環會斷。
- 各受限層的上報（escalation）需要一個收件端來通知所長並完成核准。受限層 session 自己**不該、也未必能**撈到所長 user_id 去 reply；通知與簽核一律走上報機制、由全權限層處理。

這條的完整兩 session 拓樸與身份路由見 **line-comms.md〈執行模型：核准後一條龍〉**；上報投遞 / 觸發機制見 **CLAUDE.md〈上報（escalation）機制〉**。

> **個人律所版**：只跑一個 bare `./start-line.sh`（全權限單人）即可——沒有受限層、沒有跨層上報收件問題，所長就是那個 session 本人。上面整節是多人版升級時才回來看的。

---

## 附：單一所、單一 OA（為何沒有多 OA / business_unit 設定）

律所是**單一事務所**：只有一個所內 LINE OA，所有案件、任務、時限都歸這一個所。系統的 `business_unit`（多事業體）欄位在律所版**留空 inert**——不設 `data/line-channels.json` 的多 channel 對應、也不需要 `register_business_entity` 分品牌。`.mcp.json` 用單 OA 的 `CHANNEL_ACCESS_TOKEN` / `CHANNEL_SECRET`（第一節）即可。

> 多事業體 / 多 OA 是通用底座保留的升級路（例如將來分所或合署），個人 / 單一律所不需要、本檔不展開設定步驟。建立案件 `matter` 只需輕量的 `client_name`（委任人姓名）即可查詢，不做完整 CRM、也不綁 `business_unit`。
