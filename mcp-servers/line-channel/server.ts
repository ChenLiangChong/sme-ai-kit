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
import { createHmac } from 'crypto'
import { readFileSync, writeFileSync, mkdirSync, renameSync, existsSync } from 'fs'
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
const STATE_DIR = process.env.LINE_STATE_DIR ?? join(process.env.HOME ?? '/tmp', '.claude', 'channels', 'line')
const DB_PATH = process.env.SME_DB_PATH ?? join(process.env.HOME ?? '/tmp', 'data', 'business.db')
const PROJECT_ROOT = process.env.SME_PROJECT_ROOT ?? join(import.meta.dir, '..', '..')
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
      group_id TEXT NOT NULL UNIQUE, group_name TEXT,
      group_type TEXT DEFAULT 'other', notes TEXT,
      created_at DATETIME DEFAULT (datetime('now','localtime')),
      updated_at DATETIME DEFAULT (datetime('now','localtime'))
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

// === Access Control ===

interface Access {
  allowFrom: string[]
}

function loadAccess(): Access {
  try {
    const raw = readFileSync(join(STATE_DIR, 'access.json'), 'utf8')
    return JSON.parse(raw) as Access
  } catch {
    return { allowFrom: [] }
  }
}

function saveAccess(a: Access): void {
  mkdirSync(STATE_DIR, { recursive: true, mode: 0o700 })
  const tmp = join(STATE_DIR, 'access.json.tmp')
  writeFileSync(tmp, JSON.stringify(a, null, 2) + '\n', { mode: 0o600 })
  renameSync(tmp, join(STATE_DIR, 'access.json'))
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

async function linePush(channelId: string, to: string, text: string): Promise<void> {
  const token = getChannel(channelId).access_token
  const res = await fetch('https://api.line.me/v2/bot/message/push', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ to, messages: [{ type: 'text', text }] }),
  })
  if (!res.ok) throw new Error(`LINE push failed: ${res.status} ${await res.text()}`)
}

async function linePushFlex(channelId: string, to: string, altText: string, contents: unknown): Promise<void> {
  const token = getChannel(channelId).access_token
  const res = await fetch('https://api.line.me/v2/bot/message/push', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ to, messages: [{ type: 'flex', altText, contents }] }),
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
  } catch {}
  return { displayName: userId.slice(0, 8) + '...' }
}

function verifySignature(body: string, signature: string, channelSecret: string): boolean {
  const hash = createHmac('SHA256', channelSecret).update(body).digest('base64')
  return hash === signature
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
      'LINE 訊息以 <channel source="line" chat_id="..." user="..." user_id="..." channel_id="..." channel_name="..."> 格式到達。',
      '用 reply 工具回覆，傳入 chat_id 和 channel_id。channel_id 標示是哪個 LINE OA。',
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
          ...channelIdProp,
        },
        required: ['chat_id', 'alt_text', 'flex_json'],
      },
    },
    {
      name: 'add_allowed_user',
      description: '將 LINE user ID 加入允許清單。只有允許清單中的用戶訊息才會推送給 Claude。',
      inputSchema: {
        type: 'object' as const,
        properties: {
          user_id: { type: 'string', description: 'LINE user ID' },
          ...channelIdProp,
        },
        required: ['user_id'],
      },
    },
    {
      name: 'list_allowed_users',
      description: '列出所有在允許清單中的 LINE user ID。',
      inputSchema: {
        type: 'object' as const,
        properties: { ...channelIdProp },
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
          d.run(
            `UPDATE line_messages SET status = 'replied', reply_content = ? WHERE ${col} = ? AND direction = 'inbound' AND status IN ('queued', 'processed')`,
            [text.slice(0, 200), chatId]
          )
        } catch {}
        return { content: [{ type: 'text' as const, text: `✅ 已送出（${getChannel(chId).name}）` }] }
      }
      case 'reply_flex': {
        const chatId = args.chat_id as string
        const altText = args.alt_text as string
        const flexJson = JSON.parse(args.flex_json as string)
        await linePushFlex(chId, chatId, altText, flexJson)
        const isGroupFlex = chatId.startsWith('C') || chatId.startsWith('R')
        saveMessageToDb(
          chId, `sent_${Date.now()}`, isGroupFlex ? '' : chatId, '', isGroupFlex ? 'group' : 'user',
          isGroupFlex ? chatId : null, 'outbound', `[Flex] ${altText}`, 'flex', 'replied'
        )
        try {
          const d = getDb()
          const col = isGroupFlex ? 'group_id' : 'user_id'
          d.run(
            `UPDATE line_messages SET status = 'replied' WHERE ${col} = ? AND direction = 'inbound' AND status IN ('queued', 'processed')`,
            [chatId]
          )
        } catch {}
        return { content: [{ type: 'text' as const, text: `✅ Flex Message 已送出（${getChannel(chId).name}）` }] }
      }
      case 'add_allowed_user': {
        const userId = args.user_id as string
        const access = loadAccess()
        if (!access.allowFrom.includes(userId)) {
          access.allowFrom.push(userId)
          saveAccess(access)
        }
        const profile = await lineGetProfile(chId, userId)
        return { content: [{ type: 'text' as const, text: `✅ 已允許 ${profile.displayName} (${userId})` }] }
      }
      case 'list_allowed_users': {
        const access = loadAccess()
        if (access.allowFrom.length === 0) {
          return { content: [{ type: 'text' as const, text: '允許清單為空。用 add_allowed_user 新增用戶。' }] }
        }
        const lines: string[] = []
        for (const uid of access.allowFrom) {
          const profile = await lineGetProfile(chId, uid)
          lines.push(`- ${profile.displayName}: ${uid}`)
        }
        return { content: [{ type: 'text' as const, text: `允許清單：\n${lines.join('\n')}` }] }
      }
      case 'multicast': {
        const userIds = JSON.parse(args.user_ids as string) as string[]
        const text = args.text as string
        if (!Array.isArray(userIds) || userIds.length === 0) {
          return { content: [{ type: 'text' as const, text: '❌ user_ids 必須是非空 JSON 陣列' }], isError: true }
        }
        if (userIds.length > 500) {
          return { content: [{ type: 'text' as const, text: '❌ 單次群發上限 500 人' }], isError: true }
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
          const result = d.run(
            `UPDATE line_messages SET status = 'processed' WHERE user_id = ? AND direction = 'inbound' AND status = 'queued'`,
            [chatId]
          )
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
          if (ch.business_unit) lines.push(`  事業部: ${ch.business_unit}`)
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

// === Webhook HTTP Server（路徑路由多 OA）===

const profileCache = new Map<string, string>()

if (portAlreadyInUse) {
  process.stderr.write(`line-channel: port ${WEBHOOK_PORT} 已有另一個 instance 在跑，共用現有 webhook server\n`)
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

            // Access control
            const access = loadAccess()
            if (access.allowFrom.length > 0 && !access.allowFrom.includes(userId)) {
              continue
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
              await mcp.notification({
                method: 'notifications/claude/channel',
                params: {
                  content,
                  meta: {
                    channel_id: channelId,
                    channel_name: channel.name,
                    chat_id: String(chatId),
                    message_id: String(msg.id ?? ''),
                    user: String(displayName),
                    user_id: String(userId),
                    source_type: String(sourceType),
                    ts: new Date(event.timestamp ?? Date.now()).toISOString(),
                  },
                },
              })
            } else if (event.type === 'follow') {
              await mcp.notification({
                method: 'notifications/claude/channel',
                params: {
                  content: `${displayName} 加入追蹤`,
                  meta: {
                    channel_id: channelId,
                    channel_name: channel.name,
                    chat_id: String(userId),
                    user: String(displayName),
                    user_id: String(userId),
                    event_type: 'follow',
                  },
                },
              })
            } else if (event.type === 'join') {
              const groupId = event.source?.groupId ?? chatId
              process.stderr.write(`line-channel: [${channel.name}] Bot 被加入群組 ${groupId}\n`)
              await mcp.notification({
                method: 'notifications/claude/channel',
                params: {
                  content: `Bot 被加入新的 LINE 群組`,
                  meta: {
                    channel_id: channelId,
                    channel_name: channel.name,
                    chat_id: String(groupId),
                    event_type: 'join',
                    source_type: String(sourceType),
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
  } catch (e) {
    process.stderr.write(`line-channel: port ${WEBHOOK_PORT} 綁定失敗: ${e}\n`)
    process.stderr.write(`line-channel: webhook server 未啟動，僅 MCP tools 可用\n`)
  }
}

// === ngrok 固定域名 + LINE Webhook 自動設定（多 OA）===

async function autoSetupNgrok(): Promise<void> {
  if (portAlreadyInUse) {
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
  setTimeout(() => process.exit(0), 2000)
}
process.stdin.on('end', shutdown)
process.stdin.on('close', shutdown)
process.on('SIGTERM', shutdown)
process.on('SIGINT', shutdown)
