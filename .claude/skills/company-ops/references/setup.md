# 環境設定指南

## 觸發情境

**系統導入**：首次開啟 Claude 時，`.mcp.json` 裡沒有 `line` server，或 LINE 工具無法使用。

---

## 一、LINE Channel 設定

### 前提

顧問已事先完成：
- ngrok 帳號註冊 + 固定域名
- LINE Developers Console 建立 Messaging API Channel
- LINE Official Account 開通

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

### 驗證失敗處理

| 症狀 | 可能原因 | 修法 |
|------|---------|------|
| business-db tools 無法呼叫 | .mcp.json 路徑錯 | 檢查 python3 和 server.py 路徑 |
| line tools 無法呼叫 | token/secret 錯或 bun 路徑錯 | 重新檢查 .mcp.json 的 line 區塊 |
| ngrok curl 失敗 | ngrok 沒啟動或域名錯 | 檢查 NGROK_DOMAIN 和 authtoken |
| LINE 收不到訊息 | webhook URL 沒設好 | 到 LINE Console 手動確認 webhook URL |

---

## 三、Claude Desktop 設定（選配）

如果老闆也要用 Claude Desktop / Cowork：

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
- ngrok 免費帳號每月有流量限制，正常使用足夠

---

## 五、部門安全層（floor）部署

LINE-runtime 可以「分層」啟動：不同部門的 session 套不同的可信邊界，限制各層只看得到該看的資料、各層的 DB 工具白名單也不同。**這裡只講「怎麼起、要準備哪些檔」；floor 兩道牆的把關演算法、SME_FLOOR 三態語義，見 CLAUDE.md〈部門安全層（floor）與兩道牆〉，不在此重述。**

### Step 1：用 start-line.sh `<層>` 受限啟動

`start-line.sh` 是 LINE-runtime 的啟動入口，帶一個 layer 參數決定這個 session 屬於哪一層：

```bash
./start-line.sh                # 不帶層 = 全權限（floor = data/、settings = .claude/line-runtime-settings.json）
./start-line.sh general        # 一般部門層（floor = data/general、settings = .claude/line-runtime-general.json）
./start-line.sh <層名>         # 任一已建好資料夾 + settings 的層
```

`start-line.sh <層>` 啟動受限層時會：注入 `SME_FLOOR=<層>`（business-db 據此套該層工具白名單＝第二道牆）、把 `cwd` 設成該層資料夾、載入該層 sandbox settings `.claude/line-runtime-<層>.json`（第一道牆）、並以 `--tools` built-in 白名單啟動；不帶層 ＝ `SME_FLOOR` 空 ＝ 全權限。**兩道牆 / 三態 / 工具白名單 / denyRead 清單的機制細節見 CLAUDE.md〈部門安全層（floor）與兩道牆〉——這裡只管部署要對齊什麼：**

起層前的前置條件（腳本會檢查、缺就 fail）：該層的資料夾 `data/<層>/` 要存在、該層 settings `.claude/line-runtime-<層>.json` 要存在。**這兩個都要對齊 floor-map（見 Step 2）裡的層名。**

> **不要在這裡寫死具體部門層清單**（會計 / 人資 / 內勤 / 業務 / 對外）。哪些層、各層看哪些 BU / 財務，是導入時老闆拍板的客製設定，用 Step 2 的範例檔當起點即可。

### Step 2：floor-map.json ＝ 能力設定層

各層「能看哪些財務 / 是什麼角色 / 上報給誰」不寫死在腳本，而是集中在一張能力設定表。範例檔在 `mcp-servers/business-db/floor-map.example.json`，導入時**複製成 `data/floor-map.json` 並改成這家公司的實際部門 / 品牌**：

```bash
cp mcp-servers/business-db/floor-map.example.json data/floor-map.json
# 再依老闆拍板的部門結構改 floors 內容
```

每層可設的欄位（語義以範例檔 `_fields` 為準）：

| 欄位 | 作用 |
|------|------|
| `financial_visibility` | `none`（看不到財務、預設）/ `all`（看全部財務，如會計層）/ `own_bu`（只看自己 BU 的財務、待 #11；目前 fail-closed 等同 none）。決定這層的 MCP 進程**有沒有財務工具** |
| `role` | `boss` / `manager` / `staff`，給上報與 HITL 判斷用 |
| `escalation_target` | 上報給誰：填 LINE user_id＝系統特判直送；其餘值（如 `'boss'`）走 `role=boss` → `admin` → `company.boss_line_id` 的 coalesce。（**目前未實作「填 floor 名」當收件人**）|
| `business_units` | 此層可碰哪些事業體（待 #11 BU-scoping 才真正生效）|
| `department` | 人看的部門標籤 |

無 `data/floor-map.json` 時系統走安全預設（全權限層看全部、其餘 `financial_visibility=none` / `role=staff` / 上報 `boss`），等同未啟用分層、向後相容。`floor-map.json` 屬機密設定、應在各受限層 settings 的 `denyRead` 內（範例 settings 已含）。

> floor-map 的 `financial_visibility` 直接決定「哪一層能真正記帳 / 收款 / 退款」——`record_transaction` / `record_payment` 等財務工具只在有財務可見度的層存在，受限層即使核准了審核也記不了帳、要落在有財務工具的層（通常是全權限層）。（`create_order` **不在** floor 移除清單、任何層都呼得到，只是超門檻仍走 HITL gate、不受 `financial_visibility` 控。）此分工的完整一條龍見 **line-comms.md 第六節「執行模型」**。

### Step 3：必須常駐一個全權限 session

分層部署時，**必須常駐一個 `SME_FLOOR=confidential` 的 session**（`./start-line.sh confidential`）。注意：bare `./start-line.sh`（`SME_FLOOR` 空）雖然工具上也是全權限，但老闆 / admin 的 LINE 訊息被 line-channel **硬路由到 `confidential` 層**（`server.ts` 的 `BOSS_TARGET_FLOOR='confidential'`、待 #13 改由 floor-map 推導）——只有 `confidential` session 收得到、才接得住核准閉環。理由：

- 老闆 / admin 的 LINE 訊息（含「核准 #N」）會被路由進全權限 session；沒有這層，老闆的核准訊息**無處落地**、in-session push 的「核准 → 執行 → 回覆」閉環會斷。
- 各受限層的上報（escalation）需要一個收件端來通知老闆並完成核准。受限層 session 自己**不該、也未必能**撈到老闆 user_id 去 reply；通知與簽核一律走上報機制、由全權限層處理。

這條的完整兩 session 拓樸與身份路由見 **line-comms.md 第六節「執行模型」**；上報投遞 / 觸發機制見 **CLAUDE.md〈上報（escalation）機制〉**。

---

## 多 LINE OA 設定

### 何時需要

公司有多個品牌/LINE OA，想用同一個系統管理。

### Step 1：建立 data/line-channels.json

```json
{
  "channels": {
    "brand_a": {
      "name": "品牌A 官方帳號",
      "access_token": "從 LINE Developers Console 取得",
      "channel_secret": "從 LINE Developers Console 取得",
      "business_unit": "brand_a"
    },
    "brand_b": {
      "name": "品牌B 官方帳號",
      "access_token": "...",
      "channel_secret": "...",
      "business_unit": "brand_b"
    }
  },
  "default_channel": "brand_a",
  "default_channel_id": "brand_a"
}
```

> **`business_unit` 必須對齊 `register_business_entity` 的 `entity_id`**（小寫底線，如 `brand_a` / `brand_b`，非人看的「品牌A」），否則此 OA 進來的訊息帶的 `business_unit` 跟事業體登錄對不上、按 BU 篩選 / 門檻會錯位。
>
> **`default_channel` 與 `default_channel_id` 兩個 key 都要設、同值**：目前 line-channel `server.ts` 讀 `default_channel`、cron `flush_escalations.py` 讀 `default_channel_id`，兩 reader 讀不同 key；兩者都填同一個 channel key（此例 `brand_a`）以相容兩端，待 code 統一後可收斂成一個。

### Step 2：更新 .mcp.json

移除 `CHANNEL_ACCESS_TOKEN` 和 `CHANNEL_SECRET` env vars（改由 line-channels.json 管理）。保留 `LINE_CHANNEL_PORT`、`NGROK_DOMAIN`、`SME_DB_PATH`。

### Step 3：重啟

`/exit` 然後重新 `claude`。啟動時 stderr 會顯示每個 OA 的 webhook 設定：
```
line-channel: 多 OA 模式，載入 2 個 channel（預設: brand_a）
line-channel: 品牌A 官方帳號 webhook = https://xxx.ngrok-free.app/webhook/brand_a
line-channel: 品牌B 官方帳號 webhook = https://xxx.ngrok-free.app/webhook/brand_b
```

### 向下相容

沒有 `data/line-channels.json` 時，系統自動 fallback 到 `.mcp.json` 的 env vars（單 OA 模式）。現有部署不受影響。
