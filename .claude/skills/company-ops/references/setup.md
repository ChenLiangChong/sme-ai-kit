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
2. **line channel**：嘗試 `list_allowed_users()` — 如果能跑就代表 LINE MCP 正常
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
