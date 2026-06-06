#!/usr/bin/env bun
/**
 * SME-AI-Kit LINE Channel for Claude Code
 *
 * 將 LINE 訊息即時推送進 Claude Code session。
 * 基於 Claude Code Channels (research preview) 機制。
 * 支援多 LINE OA（多品牌）：單 process、單 port、路徑路由。
 *
 * 架構：
 * LINE 用戶發訊息 → LINE Webhook → 本地 HTTP server → MCP notification → Claude session
 * Claude 回覆 → reply tool → LINE Push API → 用戶收到
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from '@modelcontextprotocol/sdk/types.js'
import { createHmac, randomBytes, timingSafeEqual } from 'crypto'
import { homedir } from 'os'
import { readFileSync, writeFileSync, mkdirSync, existsSync, unlinkSync } from 'fs'
import { join } from 'path'
import { Database } from 'bun:sqlite'

// === 多 Channel 設定 ===

interface ChannelConfig {
  id: string
  name: string
  access_token: string
  channel_secret: string
  business_unit?: string
}

interface ChannelsFile {
  channels: Record<string, {
    name: string
    access_token: string
    channel_secret: string
    business_unit?: string
  }>
  default_channel?: string
}

const WEBHOOK_PORT = Number(process.env.LINE_CHANNEL_PORT ?? 8789)
// STATE_DIR fallback 用 homedir()（不用 HOME ?? '/tmp'）：與 business-db 的 os.path.expanduser('~')
// 對齊（兩端算出同一路徑，注入才送得到），且避免 HOME 缺失時落到 floor 可寫的 /tmp＝fence 破口。
const STATE_DIR = process.env.LINE_STATE_DIR ?? join(homedir(), '.claude', 'channels', 'line')
const PROJECT_ROOT = process.env.SME_PROJECT_ROOT ?? join(import.meta.dir, '..', '..')
// DB_PATH fallback 用 repo 內 data/business.db（與 business-db Python 預設同源），不依賴 HOME：
// resolveTargetFloor() 會讀此 DB 判 boss/admin 做身份路由；若 fallback 落到 /tmp（HOME 缺失）＝
// floored 員工可在 attacker-writable 路徑種假 boss、把自己已驗簽訊息路由進 confidential（fence 破口）。
const DB_PATH = process.env.SME_DB_PATH ?? join(PROJECT_ROOT, 'data', 'business.db')
const MEDIA_DIR = join(PROJECT_ROOT, 'data', 'media', 'line')
const NGROK_DOMAIN = process.env.NGROK_DOMAIN ?? ''

mkdirSync(MEDIA_DIR, { recursive: true })

// --- Channel loader ---

function loadChannels(): { channels: Map<string, ChannelConfig>; defaultId: string } {
  const channelsPath = join(PROJECT_ROOT, 'data', 'line-channels.json')
  const channels = new Map<string, ChannelConfig>()

  if (existsSync(channelsPath)) {
    // 多 OA 模式：從 JSON 設定檔載入
    try {
      const raw = readFileSync(channelsPath, 'utf8')
      const cfg = JSON.parse(raw) as ChannelsFile
      for (const [id, ch] of Object.entries(cfg.channels)) {
        channels.set(id, { id, ...ch })
      }
      const defaultId = cfg.default_channel && channels.has(cfg.default_channel)
        ? cfg.default_channel
        : channels.keys().next().value ?? 'default'
      if (channels.size === 0) {
        process.stderr.write('line-channel: data/line-channels.json 存在但未定義任何 channel\n')
        process.exit(1)
      }
      process.stderr.write(`line-channel: 多 OA 模式，載入 ${channels.size} 個 channel（預設: ${defaultId}）\n`)
      return { channels, defaultId }
    } catch (e) {
      process.stderr.write(`line-channel: data/line-channels.json 解析失敗: ${e}\n`)
      process.exit(1)
    }
  }

  // Fallback：單 OA 模式（env vars）
  const token = process.env.CHANNEL_ACCESS_TOKEN ?? ''
  const secret = process.env.CHANNEL_SECRET ?? ''
  if (token && secret) {
    channels.set('default', {
      id: 'default',
      name: 'LINE',
      access_token: token,
      channel_secret: secret,
    })
    process.stderr.write('line-channel: 單 OA 模式（env vars）\n')
    return { channels, defaultId: 'default' }
  }

  process.stderr.write(
    'line-channel: 沒有設定任何 LINE channel\n' +
    '  → 多 OA 模式：建立 data/line-channels.json\n' +
    '  → 單 OA 模式：設定 CHANNEL_ACCESS_TOKEN + CHANNEL_SECRET env vars\n'
  )
  process.exit(1)
}

const { channels, defaultId: defaultChannelId } = loadChannels()

// 啟動驗證
for (const [id, ch] of channels) {
  if (!ch.access_token || !ch.channel_secret) {
    process.stderr.write(`line-channel: channel "${id}" 缺少 access_token 或 channel_secret\n`)
    process.exit(1)
  }
}

function getChannel(channelId: string): ChannelConfig {
  const ch = channels.get(channelId)
  if (!ch) {
    const available = [...channels.keys()].join(', ')
    throw new Error(`未知的 channel_id: ${channelId}，可用的: ${available}`)
  }
  return ch
}

// === DB ===

let db: InstanceType<typeof Database> | null = null
function getDb(): InstanceType<typeof Database> {
  if (!db) {
    db = new Database(DB_PATH)
    db.run('PRAGMA journal_mode=WAL')
    db.run('PRAGMA foreign_keys=ON')
    db.run('PRAGMA busy_timeout=5000')
    db.run(`CREATE TABLE IF NOT EXISTS line_messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      channel_id TEXT DEFAULT 'default',
      line_message_id TEXT, user_id TEXT NOT NULL, user_name TEXT,
      source_type TEXT DEFAULT 'user', group_id TEXT,
      direction TEXT NOT NULL, content TEXT NOT NULL,
      msg_type TEXT DEFAULT 'text', status TEXT DEFAULT 'queued',
      session_id TEXT, reply_content TEXT, replied_at DATETIME,
      created_at DATETIME DEFAULT (datetime('now','localtime')),
      CHECK (direction IN ('inbound','outbound','broadcast')),
      CHECK (status IN ('queued','processed','replied'))
    )`)
    db.run(`CREATE TABLE IF NOT EXISTS line_groups (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      channel_id TEXT DEFAULT 'default',
      group_id TEXT NOT NULL, group_name TEXT,
      group_type TEXT DEFAULT 'other', notes TEXT,
      created_at DATETIME DEFAULT (datetime('now','localtime')),
      updated_at DATETIME DEFAULT (datetime('now','localtime')),
      UNIQUE(channel_id, group_id)
    )`)
    // 補新欄位（舊 DB 可能沒有 channel_id）
    try { db.run("ALTER TABLE line_messages ADD COLUMN channel_id TEXT DEFAULT 'default'") } catch {}
    try { db.run("ALTER TABLE line_groups ADD COLUMN channel_id TEXT DEFAULT 'default'") } catch {}
  }
  return db
}

function saveMessageToDb(
  channelId: string, lineMessageId: string, userId: string, userName: string,
  sourceType: string, groupId: string | null,
  direction: string, content: string, msgType: string, status: string
): void {
  try {
    const d = getDb()
    d.run(
      `INSERT INTO line_messages (channel_id, line_message_id, user_id, user_name, source_type, group_id, direction, content, msg_type, status)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [channelId, lineMessageId, userId, userName, sourceType, groupId, direction, content, msgType, status]
    )
  } catch (e) {
    process.stderr.write(`line-channel: DB 寫入失敗: ${e}\n`)
  }
}

// === LINE Content Download ===

const EXT_MAP: Record<string, string> = { image: 'jpg', video: 'mp4', audio: 'm4a', file: 'bin' }
const SUBDIR_MAP: Record<string, string> = { image: 'images', video: 'videos', audio: 'audio', file: 'files' }

async function downloadLineContent(channelId: string, messageId: string, type: string, fileName?: string): Promise<string> {
  const token = getChannel(channelId).access_token
  const ext = fileName ? fileName.split('.').pop() ?? EXT_MAP[type] ?? 'bin' : EXT_MAP[type] ?? 'bin'
  const subdir = SUBDIR_MAP[type] ?? 'files'
  const targetDir = join(MEDIA_DIR, subdir)
  mkdirSync(targetDir, { recursive: true })
  const localPath = join(targetDir, `${messageId}.${ext}`)

  const res = await fetch(`https://api-data.line.me/v2/bot/message/${messageId}/content`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`LINE content download failed: ${res.status}`)

  const buffer = await res.arrayBuffer()
  writeFileSync(localPath, Buffer.from(buffer))
  return localPath
}

// === LINE API（所有函式帶 channelId）===

// push 顯式逾時（決策 #27 / codex r3）：notifier 的 mcp__line__reply 走 linePush/linePushFlex；
// escalation 投遞租約的安全不變量是「notifier 批量(_NOTIFIER_CLAIM_BATCH) × 單筆最壞 push << _CLAIM_TTL_MIN」。
// 若 push 無逾時、單筆卡死可超過 TTL → cron 把同筆當 stale reclaim 重送（雙送）。故與 cron flush
// 的 urllib timeout=10s 對齊、把單筆 push 上限綁死。business-db/tests 有 cross-file guard 驗此常數 vs TTL/批量。
const LINE_PUSH_TIMEOUT_MS = 10_000

async function linePush(channelId: string, to: string, text: string): Promise<void> {
  const token = getChannel(channelId).access_token
  const res = await fetch('https://api.line.me/v2/bot/message/push', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ to, messages: [{ type: 'text', text }] }),
    signal: AbortSignal.timeout(LINE_PUSH_TIMEOUT_MS),
  })
  if (!res.ok) throw new Error(`LINE push failed: ${res.status} ${await res.text()}`)
}

async function linePushFlex(channelId: string, to: string, altText: string, contents: unknown): Promise<void> {
  const token = getChannel(channelId).access_token
  const res = await fetch('https://api.line.me/v2/bot/message/push', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ to, messages: [{ type: 'flex', altText, contents }] }),
    signal: AbortSignal.timeout(LINE_PUSH_TIMEOUT_MS),
  })
  if (!res.ok) throw new Error(`LINE push flex failed: ${res.status} ${await res.text()}`)
}

async function lineMulticast(channelId: string, userIds: string[], text: string): Promise<number> {
  const token = getChannel(channelId).access_token
  const res = await fetch('https://api.line.me/v2/bot/message/multicast', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ to: userIds, messages: [{ type: 'text', text }] }),
  })
  if (!res.ok) throw new Error(`LINE multicast failed: ${res.status} ${await res.text()}`)
  return userIds.length
}

async function lineGetProfile(channelId: string, userId: string): Promise<{ displayName: string }> {
  try {
    const token = getChannel(channelId).access_token
    const res = await fetch(`https://api.line.me/v2/bot/profile/${userId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (res.ok) return (await res.json()) as { displayName: string }
  } catch (e) {
    process.stderr.write(`line-channel: getProfile failed for ${userId.slice(0, 8)}: ${e}\n`)
  }
  return { displayName: userId.slice(0, 8) + '...' }
}

function verifySignature(body: string, signature: string, channelSecret: string): boolean {
  // constant-time compare（codex 全專案審 LOW）：避免用 === 對簽章做提早返回的時序比較。
  const hash = createHmac('SHA256', channelSecret).update(body).digest('base64')
  const a = Buffer.from(hash)
  const b = Buffer.from(signature || '')
  if (a.length !== b.length) return false  // timingSafeEqual 要求等長；長度不符直接拒
  return timingSafeEqual(a, b)
}

// === MCP Server（Channel 模式）===

const mcp = new Server(
  { name: 'line', version: '0.1.0' },
  {
    capabilities: {
      experimental: { 'claude/channel': {} },
      tools: {},
    },
    instructions: [
      'LINE 訊息以 <channel source="line" chat_id="..." user="..." user_id="..." channel_id="..." channel_name="..." business_unit="..."> 格式到達。',
      '用 reply 工具回覆，傳入 chat_id 和 channel_id。channel_id 標示是哪個 LINE OA。business_unit 標示該 OA 所屬的事業體。',
      '用 reply_flex 工具發送 Flex Message（卡片、按鈕等），也需傳入 channel_id。',
      '用 list_channels 查看所有已設定的 LINE OA。',
      '如果訊息包含 [圖片] 路徑，可以用 Read 工具查看圖片內容。',
    ].join('\n'),
  }
)

// --- Tool schema helper ---
const channelIdProp = {
  channel_id: { type: 'string' as const, description: 'LINE OA 的 channel_id（從訊息的 meta 取得）。省略時用預設 channel。' },
}

// Tool 定義
mcp.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: 'reply',
      description: '回覆 LINE 訊息。傳入 chat_id（從 <channel> tag 取得）和文字內容。',
      inputSchema: {
        type: 'object' as const,
        properties: {
          chat_id: { type: 'string', description: 'LINE user/group ID' },
          text: { type: 'string', description: '回覆文字' },
          message_id: { type: 'string', description: '正在回覆的那則訊息 id（從 <channel> tag 的 message_id 取得）；帶上可精準標記該則為已回覆、避免誤標同聊天室其他待處理訊息' },
          ...channelIdProp,
        },
        required: ['chat_id', 'text'],
      },
    },
    {
      name: 'reply_flex',
      description: '發送 LINE Flex Message（卡片、按鈕等進階排版）。',
      inputSchema: {
        type: 'object' as const,
        properties: {
          chat_id: { type: 'string', description: 'LINE user/group ID' },
          alt_text: { type: 'string', description: '替代文字（不支援 Flex 的裝置顯示）' },
          flex_json: { type: 'string', description: 'Flex Message JSON 內容' },
          message_id: { type: 'string', description: '正在回覆的那則訊息 id（從 <channel> tag 取得）；帶上可精準標記' },
          ...channelIdProp,
        },
        required: ['chat_id', 'alt_text', 'flex_json'],
      },
    },
    {
      name: 'multicast',
      description: '群發 LINE 訊息給多位用戶。傳入 user_ids（JSON 陣列）和文字內容。上限 500 人/次。',
      inputSchema: {
        type: 'object' as const,
        properties: {
          user_ids: { type: 'string', description: 'JSON 陣列的 LINE user IDs，例如 ["Uabc","Udef"]' },
          text: { type: 'string', description: '訊息文字' },
          ...channelIdProp,
        },
        required: ['user_ids', 'text'],
      },
    },
    {
      name: 'mark_read',
      description: '標記某用戶的 LINE 訊息為已處理（不需要回覆的情況）。',
      inputSchema: {
        type: 'object' as const,
        properties: {
          chat_id: { type: 'string', description: 'LINE user/group ID' },
          message_id: { type: 'string', description: '要標記已處理的那則訊息 id（從 <channel> tag 取得）；帶上可精準標記該則、不掃掉同聊天室其他訊息' },
          ...channelIdProp,
        },
        required: ['chat_id'],
      },
    },
    {
      name: 'list_channels',
      description: '列出所有已設定的 LINE OA（Official Account）。',
      inputSchema: {
        type: 'object' as const,
        properties: {},
      },
    },
  ],
}))

// Tool 執行
mcp.setRequestHandler(CallToolRequestSchema, async (req) => {
  const args = (req.params.arguments ?? {}) as Record<string, unknown>
  const chId = (args.channel_id as string) || defaultChannelId

  try {
    switch (req.params.name) {
      case 'reply': {
        const chatId = args.chat_id as string
        const text = args.text as string
        await linePush(chId, chatId, text)
        const isGroup = chatId.startsWith('C') || chatId.startsWith('R')
        saveMessageToDb(
          chId, `sent_${Date.now()}`, isGroup ? '' : chatId, '', isGroup ? 'group' : 'user',
          isGroup ? chatId : null, 'outbound', text, 'text', 'replied'
        )
        try {
          const d = getDb()
          const col = isGroup ? 'group_id' : 'user_id'
          const msgId = (args.message_id as string) || ''
          // per-message ack（codex 全專案審 MED）：帶 message_id → 精準標記那一則（首選、不誤動其他）；
          // 沒帶 → FIFO 只結清最舊一筆 pending inbound（向後相容、不再一次標掉全部）。
          if (msgId) {
            d.run(
              `UPDATE line_messages SET status = 'replied', reply_content = ? WHERE line_message_id = ?
                 AND channel_id = ? AND direction = 'inbound' AND status IN ('queued', 'processed')`,
              [text.slice(0, 200), msgId, chId]
            )
          } else {
            d.run(
              `UPDATE line_messages SET status = 'replied', reply_content = ? WHERE id = (
                 SELECT id FROM line_messages WHERE ${col} = ? AND channel_id = ?
                 AND direction = 'inbound' AND status IN ('queued', 'processed')
                 ORDER BY id ASC LIMIT 1)`,
              [text.slice(0, 200), chatId, chId]
            )
          }
        } catch (e) {
          process.stderr.write(`line-channel: reply DB status update failed: ${e}\n`)
        }
        clearActiveRequest()
        return { content: [{ type: 'text' as const, text: `✅ 已送出（${getChannel(chId).name}）` }] }
      }
      case 'reply_flex': {
        const chatId = args.chat_id as string
        const altText = args.alt_text as string
        let flexJson: unknown
        try {
          flexJson = JSON.parse(args.flex_json as string)
        } catch (e) {
          return { content: [{ type: 'text' as const, text: `❌ flex_json 格式錯誤: ${e}` }], isError: true }
        }
        await linePushFlex(chId, chatId, altText, flexJson)
        const isGroupFlex = chatId.startsWith('C') || chatId.startsWith('R')
        saveMessageToDb(
          chId, `sent_${Date.now()}`, isGroupFlex ? '' : chatId, '', isGroupFlex ? 'group' : 'user',
          isGroupFlex ? chatId : null, 'outbound', `[Flex] ${altText}`, 'flex', 'replied'
        )
        try {
          const d = getDb()
          const col = isGroupFlex ? 'group_id' : 'user_id'
          const msgId = (args.message_id as string) || ''
          // per-message ack（codex 全專案審 MED）：帶 message_id 精準標記、否則 FIFO 最舊一筆
          if (msgId) {
            d.run(
              `UPDATE line_messages SET status = 'replied' WHERE line_message_id = ?
                 AND channel_id = ? AND direction = 'inbound' AND status IN ('queued', 'processed')`,
              [msgId, chId]
            )
          } else {
            d.run(
              `UPDATE line_messages SET status = 'replied' WHERE id = (
                 SELECT id FROM line_messages WHERE ${col} = ? AND channel_id = ?
                 AND direction = 'inbound' AND status IN ('queued', 'processed')
                 ORDER BY id ASC LIMIT 1)`,
              [chatId, chId]
            )
          }
        } catch (e) {
          process.stderr.write(`line-channel: reply_flex DB status update failed: ${e}\n`)
        }
        clearActiveRequest()
        return { content: [{ type: 'text' as const, text: `✅ Flex Message 已送出（${getChannel(chId).name}）` }] }
      }
      case 'multicast': {
        let userIds: string[]
        try {
          userIds = JSON.parse(args.user_ids as string) as string[]
        } catch (e) {
          return { content: [{ type: 'text' as const, text: `❌ user_ids JSON 格式錯誤: ${e}` }], isError: true }
        }
        const text = args.text as string
        if (!Array.isArray(userIds) || userIds.length === 0) {
          return { content: [{ type: 'text' as const, text: '❌ user_ids 必須是非空 JSON 陣列' }], isError: true }
        }
        if (userIds.length > 500) {
          return { content: [{ type: 'text' as const, text: '❌ 單次群發上限 500 人' }], isError: true }
        }
        if (text.length > 5000) {
          return { content: [{ type: 'text' as const, text: `❌ 訊息長度 ${text.length} 超過 LINE 上限 5000 字元` }], isError: true }
        }
        const sent = await lineMulticast(chId, userIds, text)
        saveMessageToDb(
          chId, `broadcast_${Date.now()}`, 'system', '', 'broadcast', null,
          'broadcast', `[群發 ${sent} 人] ${text}`, 'text', 'replied'
        )
        return { content: [{ type: 'text' as const, text: `✅ 已群發給 ${sent} 位用戶（${getChannel(chId).name}）` }] }
      }
      case 'mark_read': {
        const chatId = args.chat_id as string
        try {
          const d = getDb()
          const isGroupMark = chatId.startsWith('C') || chatId.startsWith('R')
          const col = isGroupMark ? 'group_id' : 'user_id'
          const msgId = (args.message_id as string) || ''
          // per-message ack（codex 全專案審 MED）：帶 message_id 精準標記那一則；否則 FIFO 最舊一筆
          // queued（agent 每回合處理一則、以 reply 或 mark_read 結束之），不掃掉處理期間新到的訊息。
          const result = msgId
            ? d.run(
                `UPDATE line_messages SET status = 'processed' WHERE line_message_id = ?
                   AND channel_id = ? AND direction = 'inbound' AND status = 'queued'`,
                [msgId, chId]
              )
            : d.run(
                `UPDATE line_messages SET status = 'processed' WHERE id = (
                   SELECT id FROM line_messages WHERE ${col} = ? AND channel_id = ?
                   AND direction = 'inbound' AND status = 'queued'
                   ORDER BY id ASC LIMIT 1)`,
                [chatId, chId]
              )
          clearActiveRequest()
          return { content: [{ type: 'text' as const, text: `✅ 已標記 ${result.changes} 則訊息為已處理` }] }
        } catch (e) {
          return { content: [{ type: 'text' as const, text: `❌ 標記失敗: ${e}` }], isError: true }
        }
      }
      case 'list_channels': {
        const lines: string[] = [`## LINE OA 頻道（${channels.size} 個）\n`]
        for (const [id, ch] of channels) {
          const isDefault = id === defaultChannelId ? ' ⭐ 預設' : ''
          lines.push(`- **${ch.name}** (channel_id=\`${id}\`)${isDefault}`)
          if (ch.business_unit) lines.push(`  事業體: ${ch.business_unit}`)
        }
        return { content: [{ type: 'text' as const, text: lines.join('\n') }] }
      }
      default:
        return {
          content: [{ type: 'text' as const, text: `未知工具: ${req.params.name}` }],
          isError: true,
        }
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    return {
      content: [{ type: 'text' as const, text: `❌ ${req.params.name} 失敗: ${msg}` }],
      isError: true,
    }
  }
})

// 連接 Claude Code
await mcp.connect(new StdioServerTransport())

// === 偵測 port 是否已被佔用 ===

async function isPortInUse(port: number): Promise<boolean> {
  try {
    const res = await fetch(`http://localhost:${port}/`, { signal: AbortSignal.timeout(2000) })
    const text = await res.text()
    return text.includes('LINE Channel OK')
  } catch {
    return false
  }
}

const portAlreadyInUse = await isPortInUse(WEBHOOK_PORT)

// === IPC Broadcast（多 session 共用 webhook）===

const IPC_SOCKET_PATH = join(STATE_DIR, 'broadcast.sock')
mkdirSync(STATE_DIR, { recursive: true })

// 注入入口（決策 #25，block 1）：owner 啟動時產生一次性 token 寫到 inject.token（0600），
// 只有 owner 寫此檔（單一來源、單一 token）。Py 送端（business-db commit-hook）每次送前重讀，
// 透過既有 IPC broadcast socket 送 token 化的 inject 行進來、owner 比對 token 後轉呼 notifyAll。
// 走 socket 不走 HTTP port：沙箱不隔離網路（agent 可 curl localhost），但 socket 在 ~/.claude 下、
// 被 LINE-runtime sandbox 檔案系統 + denyRead 擋住。owner 關閉時連 socket 一起 unlink。
const INJECT_TOKEN_PATH = join(STATE_DIR, 'inject.token')
let injectToken = ''

// active-request（決策 #162/#163）：每則驗簽後寫 verified user_id，給 business-db 當「可信操作者」來源。
// agent 碰不到——檔在 ~/.claude 下、被 LINE-runtime sandbox denyRead；只有非 sandbox 的 MCP 進程讀得到。
// 回覆 / 標記已讀後清除（single-flight 生命週期）。多 session 定向派送時改為 per-floor（#4c）。
// active-request per-floor（決策 #164）：寫到「目標層」的檔，各層 session 的 business-db 只讀自己層的，
// 避免多層同時在線時跨層覆蓋誤歸因。owner 依算出的 target_floor 寫；instance 回覆後清自己層的。
function activeReqPath(floor: string): string {
  return join(STATE_DIR, `active-request-${floor || 'none'}.json`)
}
function writeActiveRequest(targetFloor: string, meta: Record<string, unknown>): void {
  try {
    writeFileSync(activeReqPath(targetFloor), JSON.stringify({ ...meta, target_floor: targetFloor, written_ms: Date.now() }))
  } catch (e) {
    process.stderr.write(`line-channel: writeActiveRequest failed: ${e}\n`)
  }
}
function clearActiveRequest(): void {
  // 在「回覆的那個 instance」執行 → 清自己這層的 active-request
  try {
    const p = activeReqPath(myFloor())
    if (existsSync(p)) unlinkSync(p)
  } catch {}
}

// 廣播追蹤：webhook owner 用這個 set 追蹤連線的 IPC clients
const ipcClients = new Set<ReturnType<typeof Bun.listen> extends { socket: infer S } ? S : any>()

function broadcastNotification(payload: { method: string; params: Record<string, unknown> }): void {
  if (ipcClients.size === 0) return
  const data = JSON.stringify(payload) + '\n'
  for (const client of ipcClients) {
    try {
      client.write(data)
    } catch {
      ipcClients.delete(client)
    }
  }
}

// === 分流派送（決策 #164）===
// 軸B：這則訊息該去哪一層。MVP：floor-map.json 還沒建（=onboarding #6 產物），
// 先用 channel.business_unit、否則 DEFAULT_FLOOR。TODO #6：讀 floor-map 做 employees.department→floor 收斂。
const DEFAULT_FLOOR = process.env.SME_DEFAULT_FLOOR || 'general'
function lookupFloor(channelBusinessUnit: string): string {
  return channelBusinessUnit || DEFAULT_FLOOR
}
// 身份路由（決策 #25，block 3）：全權限主體（老闆 / admin）的可信 LINE 訊息一律落 confidential 層，
// 讓「核准 #N」進入「能 resolve + 執行」的全權限 session。與 shared/escalation.py 的 BOSS_TARGET_FLOOR 一致。
const BOSS_TARGET_FLOOR = 'confidential'
// sender 經 webhook 簽章驗證故可信：查 employees 是否有 active 全權限列且 line_user_id 相符。
// 查到 → confidential；查無（非全權限）→ lookupFloor 部門層；DB 例外 → fail-closed 收斂到
// confidential（不降級送部門層、避免 boss 訊息落員工 session ＝跨硬牆洩漏；寧過度路由、不洩漏）。
// 只有 owner 跑 webhook、故只有 owner 需要查；用 owner 的 getDb()。
function resolveTargetFloor(channelBusinessUnit: string, userId: string): string {
  if (!userId) return lookupFloor(channelBusinessUnit)
  try {
    const row = getDb()
      .query(
        `SELECT 1 FROM employees WHERE active=1 AND line_user_id=? AND (role='boss' OR permissions='admin') LIMIT 1`,
      )
      .get(userId)
    if (row) return BOSS_TARGET_FLOOR
  } catch (e) {
    // fail-closed：查不動 DB 無法判定身份 → 收斂到全權限層（只有老闆看得到）、不降級送部門層。
    process.stderr.write(`line-channel: resolveTargetFloor DB 查詢失敗、fail-closed 回 confidential: ${e}\n`)
    return BOSS_TARGET_FLOOR
  }
  return lookupFloor(channelBusinessUnit)
}
// 本 instance 啟動參數 SME_FLOOR（軸A）。展開失敗的 ${...} 視為受限未知層（matches nothing=fail-closed），
// 不誤當無參數；真正無參數('')才是 operator/向後相容（收全部）。
function myFloor(): string {
  const v = process.env.SME_FLOOR || ''
  if (v.includes('$') || v.includes('{')) return '__unexpanded__'
  return v
}
// 接收端 self-filter：用本 instance 的 myFloor 決定這則要不要送進自己的 channel。
function shouldDeliver(targetFloor: unknown): boolean {
  const my = myFloor()
  if (my === '') return true // operator / 向後相容單一 session → 收全部
  return my === targetFloor
}

// 通知：自己這層才 emit channel；IPC 一律廣播給所有 instance（各自 self-filter）。
async function notifyAll(notification: { method: string; params: Record<string, unknown> }): Promise<void> {
  const tf = (notification.params?.meta as Record<string, unknown> | undefined)?.target_floor
  if (shouldDeliver(tf)) await mcp.notification(notification)
  broadcastNotification(notification)
}

// === Webhook HTTP Server（路徑路由多 OA）===

const profileCache = new Map<string, string>()

// IPC client：連到 owner 的 broadcast socket 接收 webhook 事件。兩條路會用到——
// ① 啟動時偵測 port 已被佔（portAlreadyInUse）；② owner 選舉 TOCTOU：本以為沒人、Bun.serve
// 綁 port 卻失敗（被別 instance 搶先），退回當 client、不再 stranding（codex 全專案審 MED）。
let ipcBuffer = ''
let ipcConnected = false
let ownerBindFailed = false  // TOCTOU：以為自己是 owner 但 Bun.serve 綁 port 失敗 → 退回 client、ngrok 跳過
function connectIpc(): void {
  if (ipcConnected) return
  ipcConnected = true
    Bun.connect({
      unix: IPC_SOCKET_PATH,
      socket: {
        open(socket) {
          process.stderr.write('line-channel: IPC 已連線，開始接收 webhook 廣播\n')
        },
        data(socket, data) {
          ipcBuffer += Buffer.from(data).toString()
          const lines = ipcBuffer.split('\n')
          ipcBuffer = lines.pop() ?? ''
          for (const line of lines) {
            if (!line.trim()) continue
            try {
              const payload = JSON.parse(line)
              const tf = (payload?.params?.meta as Record<string, unknown> | undefined)?.target_floor
              if (shouldDeliver(tf)) {
                process.stderr.write(`line-channel: IPC 廣播→送進 channel (self=${myFloor()})\n`)
                mcp.notification(payload).catch(() => {})
              } else {
                process.stderr.write(`line-channel: IPC 廣播非本層、不送 channel (target=${tf} self=${myFloor()})\n`)
              }
            } catch (e) {
              process.stderr.write(`line-channel: IPC 訊息解析失敗: ${e}\n`)
            }
          }
        },
        close(socket) {
          process.stderr.write('line-channel: IPC 斷線，3 秒後重連\n')
          ipcConnected = false
          setTimeout(connectIpc, 3000)
        },
        error(socket, err) {
          // close handler will handle reconnect
        },
      },
    }).catch(() => {
      process.stderr.write('line-channel: IPC 連線失敗，3 秒後重試\n')
      ipcConnected = false
      setTimeout(connectIpc, 3000)
    })
}

if (portAlreadyInUse) {
  process.stderr.write(`line-channel: port ${WEBHOOK_PORT} 已有另一個 instance，連線 IPC 接收廣播\n`)
  connectIpc()
} else {
  try {
    Bun.serve({
      port: WEBHOOK_PORT,
      hostname: '0.0.0.0',
      async fetch(req) {
        const url = new URL(req.url)

        // Health check
        if (req.method === 'GET') {
          return new Response('LINE Channel OK')
        }

        if (req.method !== 'POST') {
          return new Response('404', { status: 404 })
        }

        // 路由：/webhook/:channel_id 或 /webhook（legacy → default）
        let channelId: string
        const pathMatch = url.pathname.match(/^\/webhook\/([a-zA-Z0-9_-]+)$/)
        if (pathMatch) {
          channelId = pathMatch[1]
        } else if (url.pathname === '/' || url.pathname === '/webhook') {
          channelId = defaultChannelId
        } else {
          return new Response('404', { status: 404 })
        }

        const channel = channels.get(channelId)
        if (!channel) {
          return new Response(`unknown channel: ${channelId}`, { status: 404 })
        }

        const body = await req.text()
        const signature = req.headers.get('x-line-signature') ?? ''

        if (!verifySignature(body, signature, channel.channel_secret)) {
          return new Response('invalid signature', { status: 401 })
        }

        try {
          const payload = JSON.parse(body)

          for (const event of payload.events ?? []) {
            const userId = event.source?.userId ?? ''
            const chatId = event.source?.groupId ?? event.source?.roomId ?? userId
            const sourceType = event.source?.type ?? 'user'

            // 群組訊息：只處理 @mention
            if (sourceType === 'group' || sourceType === 'room') {
              if (event.type === 'message' && event.message?.type === 'text') {
                const mention = event.message.mention
                if (!mention?.mentionees?.length) continue
                let text = event.message.text as string
                for (const m of [...mention.mentionees].sort((a: any, b: any) => (b.index ?? 0) - (a.index ?? 0))) {
                  text = text.slice(0, m.index ?? 0) + text.slice((m.index ?? 0) + (m.length ?? 0))
                }
                event.message.text = text.trim()
              } else if (event.type !== 'join') {
                continue
              }
            }

            // 取得用戶暱稱（帶 channelId 快取）
            const cacheKey = `${channelId}:${userId}`
            let displayName = profileCache.get(cacheKey)
            if (!displayName && userId) {
              const profile = await lineGetProfile(channelId, userId)
              displayName = profile.displayName
              profileCache.set(cacheKey, displayName)
            }
            displayName = displayName || 'unknown'

            if (event.type === 'message') {
              const msg = event.message
              let content = ''

              switch (msg.type) {
                case 'text':
                  content = msg.text ?? ''
                  break
                case 'image': {
                  try {
                    const imgPath = await downloadLineContent(channelId, String(msg.id), 'image')
                    content = `[圖片] ${imgPath}`
                  } catch {
                    content = '[圖片] (下載失敗)'
                  }
                  break
                }
                case 'video':
                  content = '[影片] (語音/影片辨識需額外 STT 工具，暫不支援)'
                  break
                case 'audio':
                  content = '[語音] (語音辨識需額外 STT 工具，暫不支援)'
                  break
                case 'sticker':
                  content = '[貼圖]'
                  break
                case 'location':
                  content = `[位置: ${msg.title ?? ''} ${msg.address ?? ''}]`
                  break
                case 'file': {
                  try {
                    const filePath = await downloadLineContent(channelId, String(msg.id), 'file', (msg as any).fileName)
                    content = `[檔案] ${filePath} (${(msg as any).fileName ?? '未知檔名'})`
                  } catch {
                    content = `[檔案: ${(msg as any).fileName ?? ''}] (下載失敗)`
                  }
                  break
                }
                default:
                  content = `[${msg.type}]`
              }

              saveMessageToDb(
                channelId, String(msg.id ?? ''), String(userId), String(displayName),
                String(sourceType), sourceType !== 'user' ? String(chatId) : null,
                'inbound', content, String(msg.type), 'queued'
              )

              process.stderr.write(`line-channel: [${channel.name}] 推送訊息 from=${displayName} content=${content.slice(0, 50)}\n`)
              // 身份路由（block 3）：全權限主體（老闆 / admin）的可信訊息改解析為 confidential，
              // 否則維持既有 lookupFloor 行為。writeActiveRequest 與 notifyAll meta.target_floor 同用此變數。
              const targetFloor = resolveTargetFloor(channel.business_unit || '', String(userId))
              writeActiveRequest(targetFloor, {
                channel_id: channelId,
                business_unit: channel.business_unit || '',
                chat_id: String(chatId),
                message_id: String(msg.id ?? ''),
                user_id: String(userId),
                user: String(displayName),
                source_type: String(sourceType),
              })
              await notifyAll({
                method: 'notifications/claude/channel',
                params: {
                  content,
                  meta: {
                    channel_id: channelId,
                    channel_name: channel.name,
                    business_unit: channel.business_unit || '',
                    chat_id: String(chatId),
                    message_id: String(msg.id ?? ''),
                    user: String(displayName),
                    user_id: String(userId),
                    source_type: String(sourceType),
                    target_floor: targetFloor,
                    ts: new Date(event.timestamp ?? Date.now()).toISOString(),
                  },
                },
              })
            } else if (event.type === 'follow') {
              await notifyAll({
                method: 'notifications/claude/channel',
                params: {
                  content: `${displayName} 加入追蹤`,
                  meta: {
                    channel_id: channelId,
                    channel_name: channel.name,
                    business_unit: channel.business_unit || '',
                    chat_id: String(userId),
                    user: String(displayName),
                    user_id: String(userId),
                    event_type: 'follow',
                    target_floor: lookupFloor(channel.business_unit || ''),
                  },
                },
              })
            } else if (event.type === 'join') {
              const groupId = event.source?.groupId ?? chatId
              process.stderr.write(`line-channel: [${channel.name}] Bot 被加入群組 ${groupId}\n`)
              await notifyAll({
                method: 'notifications/claude/channel',
                params: {
                  content: `Bot 被加入新的 LINE 群組`,
                  meta: {
                    channel_id: channelId,
                    channel_name: channel.name,
                    business_unit: channel.business_unit || '',
                    chat_id: String(groupId),
                    event_type: 'join',
                    source_type: String(sourceType),
                    target_floor: lookupFloor(channel.business_unit || ''),
                    ts: new Date(event.timestamp ?? Date.now()).toISOString(),
                  },
                },
              })
            }
          }

          return new Response('ok')
        } catch (err) {
          process.stderr.write(`line-channel: webhook 處理失敗: ${err}\n`)
          return new Response('internal error', { status: 500 })
        }
      },
    })
    process.stderr.write(`line-channel: webhook 監聽中 http://localhost:${WEBHOOK_PORT}/webhook\n`)

    // 啟動 IPC broadcast server，讓其他 session 可以接收 webhook 事件
    try { unlinkSync(IPC_SOCKET_PATH) } catch {}
    // 注入 token（block 1）：owner 產生一次性 token 並寫出（0600），供 Py 送端讀取後附在 inject 行驗證。
    // 先刪殘留檔再寫：writeFileSync 的 mode 只對「新建檔」生效，殘留舊檔會沿用舊（可能過寬）權限。
    try { unlinkSync(INJECT_TOKEN_PATH) } catch {}
    injectToken = randomBytes(24).toString('hex')
    try {
      writeFileSync(INJECT_TOKEN_PATH, injectToken, { mode: 0o600 })
      process.stderr.write(`line-channel: inject token 已寫出 ${INJECT_TOKEN_PATH}\n`)
    } catch (e) {
      process.stderr.write(`line-channel: inject token 寫出失敗: ${e}\n`)
    }
    try {
      Bun.listen({
        unix: IPC_SOCKET_PATH,
        socket: {
          open(socket: any) {
            ipcClients.add(socket)
            process.stderr.write(`line-channel: IPC client 連線（共 ${ipcClients.size} 個 session）\n`)
          },
          close(socket: any) {
            ipcClients.delete(socket)
            process.stderr.write(`line-channel: IPC client 斷線（剩 ${ipcClients.size} 個 session）\n`)
          },
          data(socket: any, data: any) {
            // 注入入口（block 1）：clients 平常不送資料，唯一例外是 Py 送端的 token 化 inject 行。
            // 逐 socket 累積 buffer（暫存在 socket 物件上）、以 \n 切行、每行 JSON.parse。
            // 整段 try/catch 包住、永不外拋（data handler 非 async；notifyAll 是 async → 用 .catch 不 await）。
            try {
              // 防呆上限（先按原始位元組數擋、再解碼拼接）：合法 inject 為單一短行（遠小於 64KB）。
              // 巨量 frame 或無換行洪流 → 連解都不解、重置並關閉此連線、避免無界字串配置
              //（合法送端送完即關、關閉無副作用）。
              const incoming = (data?.byteLength ?? data?.length ?? 0)
              const buffered = socket._injBuf ? Buffer.byteLength(socket._injBuf, 'utf8') : 0
              if (incoming + buffered > 65536) {
                process.stderr.write('line-channel: inject 輸入超過 64KB、重置並關閉連線\n')
                socket._injBuf = ''
                try { socket.end() } catch {}
                return
              }
              socket._injBuf = (socket._injBuf ?? '') + Buffer.from(data).toString()
              const lines = socket._injBuf.split('\n')
              socket._injBuf = lines.pop() ?? ''
              for (const line of lines) {
                if (!line.trim()) continue
                let obj: any
                try {
                  obj = JSON.parse(line)
                } catch (e) {
                  process.stderr.write(`line-channel: inject 行解析失敗、忽略: ${e}\n`)
                  continue
                }
                if (
                  obj?.type === 'inject' &&
                  typeof obj.token === 'string' &&
                  obj.token === injectToken &&
                  obj.notification?.method
                ) {
                  // 不 await：data handler 非 async；投遞照既有 notifyAll（owner self-filter + IPC 廣播）。
                  notifyAll(obj.notification).catch(() => {})
                } else {
                  process.stderr.write('line-channel: inject 行 token 不符或格式錯、拒絕\n')
                }
              }
            } catch (e) {
              process.stderr.write(`line-channel: inject data handler 例外（已吞）: ${e}\n`)
            }
          },
          error(socket: any, err: any) { ipcClients.delete(socket) },
        },
      })
      process.stderr.write(`line-channel: IPC broadcast server 啟動 ${IPC_SOCKET_PATH}\n`)
    } catch (e) {
      process.stderr.write(`line-channel: IPC server 啟動失敗: ${e}\n`)
    }
  } catch (e) {
    // TOCTOU（codex 全專案審 MED）：isPortInUse 偵測時沒人、Bun.serve 卻綁不上 = 別 instance
    // 搶先成為 owner。退回當 IPC client（連 owner 的 broadcast socket）、不再 stranded 收不到廣播；
    // 並標記 ownerBindFailed 讓 autoSetupNgrok 跳過（本 instance 不是 owner、不該重設 ngrok/webhook）。
    process.stderr.write(`line-channel: port ${WEBHOOK_PORT} 綁定失敗（被搶先成為 owner）: ${e}\n`)
    process.stderr.write(`line-channel: 退回 IPC client 模式接收廣播\n`)
    ownerBindFailed = true
    connectIpc()
  }
}

// === ngrok 固定域名 + LINE Webhook 自動設定（多 OA）===

async function autoSetupNgrok(): Promise<void> {
  if (portAlreadyInUse || ownerBindFailed) {
    process.stderr.write('line-channel: 跳過 ngrok（已有 instance 在處理）\n')
    return
  }

  if (!NGROK_DOMAIN) {
    process.stderr.write('line-channel: NGROK_DOMAIN 未設定，跳過 ngrok 自動設定（LINE webhook 需手動配置）\n')
    return
  }

  // 殺掉舊的 ngrok
  try {
    Bun.spawnSync(['pkill', '-f', 'ngrok'])
    await Bun.sleep(1000)
  } catch {}

  process.stderr.write(`line-channel: 啟動 ngrok --domain=${NGROK_DOMAIN} → port ${WEBHOOK_PORT}\n`)
  try {
    Bun.spawn(['ngrok', 'http', String(WEBHOOK_PORT), `--domain=${NGROK_DOMAIN}`, '--log=stdout', '--log-format=json'], {
      stdout: 'ignore',
      stderr: 'ignore',
    })
    let ngrokReady = false
    for (let i = 0; i < 20; i++) {
      await Bun.sleep(500)
      try {
        const r = await fetch('http://localhost:4040/api/tunnels', { signal: AbortSignal.timeout(1000) })
        if (r.ok) { ngrokReady = true; break }
      } catch {}
    }
    if (!ngrokReady) {
      process.stderr.write('line-channel: ngrok 未在 10 秒內就緒，webhook 可能無法使用\n')
    }
  } catch (e) {
    process.stderr.write(`line-channel: ngrok 啟動失敗（可能未安裝）: ${e}\n`)
    return
  }

  // 對每個 channel 設定 LINE webhook URL
  for (const [id, ch] of channels) {
    const webhookEndpoint = `https://${NGROK_DOMAIN}/webhook/${id}`
    try {
      const res = await fetch('https://api.line.me/v2/bot/channel/webhook/endpoint', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${ch.access_token}` },
        body: JSON.stringify({ endpoint: webhookEndpoint }),
      })
      if (res.ok) {
        process.stderr.write(`line-channel: ${ch.name} webhook = ${webhookEndpoint} ✅\n`)
      } else {
        process.stderr.write(`line-channel: ${ch.name} webhook 設定失敗: ${res.status}\n`)
      }
    } catch (e) {
      process.stderr.write(`line-channel: ${ch.name} webhook 設定失敗: ${e}\n`)
    }
  }
}

autoSetupNgrok().catch(e => {
  process.stderr.write(`line-channel: ngrok 設定錯誤: ${e}\n`)
})

// === Graceful Shutdown ===

let shuttingDown = false
function shutdown(): void {
  if (shuttingDown) return
  shuttingDown = true
  process.stderr.write('line-channel: 關閉中\n')
  if (!portAlreadyInUse) {
    try { unlinkSync(IPC_SOCKET_PATH) } catch {}
    // owner 關閉時連 inject token 一起 unlink（單一來源、避免殘留舊 token）。
    try { unlinkSync(INJECT_TOKEN_PATH) } catch {}
  }
  setTimeout(() => process.exit(0), 2000)
}
process.stdin.on('end', shutdown)
process.stdin.on('close', shutdown)
process.on('SIGTERM', shutdown)
process.on('SIGINT', shutdown)
