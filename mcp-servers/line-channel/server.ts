#!/usr/bin/env bun
/**
 * SME-AI-Kit LINE Channel for Claude Code
 *
 * 將 LINE 訊息即時推送進 Claude Code session。
 * 基於 Claude Code Channels (research preview) 機制。
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
import { readFileSync, writeFileSync, mkdirSync, renameSync } from 'fs'
import { join } from 'path'
import { Database } from 'bun:sqlite'

// === 設定 ===

const CHANNEL_ACCESS_TOKEN = process.env.CHANNEL_ACCESS_TOKEN ?? ''
const CHANNEL_SECRET = process.env.CHANNEL_SECRET ?? ''
const WEBHOOK_PORT = Number(process.env.LINE_CHANNEL_PORT ?? 8789)
const STATE_DIR = process.env.LINE_STATE_DIR ?? join(process.env.HOME ?? '/tmp', '.claude', 'channels', 'line')

const DB_PATH = process.env.SME_DB_PATH ?? join(process.env.HOME ?? '/tmp', 'data', 'business.db')

// Bun 內建 SQLite，零依賴
let db: InstanceType<typeof Database> | null = null
function getDb(): InstanceType<typeof Database> {
  if (!db) {
    db = new Database(DB_PATH)
    db.run('PRAGMA journal_mode=WAL')
    db.run('PRAGMA foreign_keys=ON')
  }
  return db
}

function saveMessageToDb(
  lineMessageId: string, userId: string, userName: string,
  sourceType: string, groupId: string | null,
  direction: string, content: string, msgType: string, status: string
): void {
  try {
    const d = getDb()
    d.run(
      `INSERT INTO line_messages (line_message_id, user_id, user_name, source_type, group_id, direction, content, msg_type, status)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [lineMessageId, userId, userName, sourceType, groupId, direction, content, msgType, status]
    )
  } catch (e) {
    process.stderr.write(`line-channel: DB 寫入失敗: ${e}\n`)
  }
}

if (!CHANNEL_ACCESS_TOKEN || !CHANNEL_SECRET) {
  process.stderr.write(
    'line-channel: CHANNEL_ACCESS_TOKEN 和 CHANNEL_SECRET 必須設定\n'
  )
  process.exit(1)
}

// === Access Control（允許誰跟 Claude 對話）===

interface Access {
  allowFrom: string[]  // 允許的 LINE user IDs
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

// 媒體檔存在專案 data/media/ 下（跟 DB 同級），不放 .claude/
const PROJECT_ROOT = process.env.SME_PROJECT_ROOT ?? join(import.meta.dir, '..', '..')
const MEDIA_DIR = join(PROJECT_ROOT, 'data', 'media', 'line')
mkdirSync(MEDIA_DIR, { recursive: true })

const EXT_MAP: Record<string, string> = {
  image: 'jpg',
  video: 'mp4',
  audio: 'm4a',
  file: 'bin',
}

const SUBDIR_MAP: Record<string, string> = {
  image: 'images',
  video: 'videos',
  audio: 'audio',
  file: 'files',
}

async function downloadLineContent(messageId: string, type: string, fileName?: string): Promise<string> {
  const ext = fileName ? fileName.split('.').pop() ?? EXT_MAP[type] ?? 'bin' : EXT_MAP[type] ?? 'bin'
  const subdir = SUBDIR_MAP[type] ?? 'files'
  const targetDir = join(MEDIA_DIR, subdir)
  mkdirSync(targetDir, { recursive: true })
  const localPath = join(targetDir, `${messageId}.${ext}`)

  const res = await fetch(`https://api-data.line.me/v2/bot/message/${messageId}/content`, {
    headers: { Authorization: `Bearer ${CHANNEL_ACCESS_TOKEN}` },
  })
  if (!res.ok) {
    throw new Error(`LINE content download failed: ${res.status}`)
  }

  const buffer = await res.arrayBuffer()
  writeFileSync(localPath, Buffer.from(buffer))
  return localPath
}

// === LINE API ===

async function linePush(to: string, text: string): Promise<void> {
  const res = await fetch('https://api.line.me/v2/bot/message/push', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${CHANNEL_ACCESS_TOKEN}`,
    },
    body: JSON.stringify({
      to,
      messages: [{ type: 'text', text }],
    }),
  })
  if (!res.ok) {
    throw new Error(`LINE push failed: ${res.status} ${await res.text()}`)
  }
}

async function linePushFlex(to: string, altText: string, contents: unknown): Promise<void> {
  const res = await fetch('https://api.line.me/v2/bot/message/push', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${CHANNEL_ACCESS_TOKEN}`,
    },
    body: JSON.stringify({
      to,
      messages: [{ type: 'flex', altText, contents }],
    }),
  })
  if (!res.ok) {
    throw new Error(`LINE push flex failed: ${res.status} ${await res.text()}`)
  }
}

async function lineMulticast(userIds: string[], text: string): Promise<number> {
  const res = await fetch('https://api.line.me/v2/bot/message/multicast', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${CHANNEL_ACCESS_TOKEN}`,
    },
    body: JSON.stringify({
      to: userIds,
      messages: [{ type: 'text', text }],
    }),
  })
  if (!res.ok) {
    throw new Error(`LINE multicast failed: ${res.status} ${await res.text()}`)
  }
  return userIds.length
}

async function lineGetProfile(userId: string): Promise<{ displayName: string }> {
  try {
    const res = await fetch(`https://api.line.me/v2/bot/profile/${userId}`, {
      headers: { Authorization: `Bearer ${CHANNEL_ACCESS_TOKEN}` },
    })
    if (res.ok) return (await res.json()) as { displayName: string }
  } catch {}
  return { displayName: userId.slice(0, 8) + '...' }
}

function verifySignature(body: string, signature: string): boolean {
  const hash = createHmac('SHA256', CHANNEL_SECRET).update(body).digest('base64')
  return hash === signature
}

// === MCP Server（Channel 模式）===

const mcp = new Server(
  { name: 'line', version: '0.0.1' },
  {
    capabilities: {
      experimental: {
        'claude/channel': {},
      },
      tools: {},
    },
    instructions: [
      'LINE 訊息以 <channel source="line" chat_id="..." user="..." user_id="..."> 格式到達。',
      '用 reply 工具回覆，傳入 chat_id。',
      '用 reply_flex 工具發送 Flex Message（卡片、按鈕等）。',
      '如果訊息包含 [圖片] 路徑，可以用 Read 工具查看圖片內容。',
    ].join('\n'),
  }
)

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
        },
        required: ['user_id'],
      },
    },
    {
      name: 'list_allowed_users',
      description: '列出所有在允許清單中的 LINE user ID。',
      inputSchema: {
        type: 'object' as const,
        properties: {},
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
        },
        required: ['chat_id'],
      },
    },
  ],
}))

// Tool 執行
mcp.setRequestHandler(CallToolRequestSchema, async (req) => {
  const args = (req.params.arguments ?? {}) as Record<string, unknown>
  try {
    switch (req.params.name) {
      case 'reply': {
        const chatId = args.chat_id as string
        const text = args.text as string
        await linePush(chatId, text)
        // 記錄發出的訊息
        saveMessageToDb(
          `sent_${Date.now()}`, chatId, '', 'user', null,
          'outbound', text, 'text', 'replied'
        )
        // 把該用戶的未處理訊息標記為已回覆
        try {
          const d = getDb()
          d.run(
            `UPDATE line_messages SET status = 'replied', reply_content = ? WHERE user_id = ? AND direction = 'inbound' AND status IN ('queued', 'processed')`,
            [text.slice(0, 200), chatId]
          )
        } catch {}
        return { content: [{ type: 'text' as const, text: '✅ 已送出' }] }
      }
      case 'reply_flex': {
        const chatId = args.chat_id as string
        const altText = args.alt_text as string
        const flexJson = JSON.parse(args.flex_json as string)
        await linePushFlex(chatId, altText, flexJson)
        return { content: [{ type: 'text' as const, text: '✅ Flex Message 已送出' }] }
      }
      case 'add_allowed_user': {
        const userId = args.user_id as string
        const access = loadAccess()
        if (!access.allowFrom.includes(userId)) {
          access.allowFrom.push(userId)
          saveAccess(access)
        }
        const profile = await lineGetProfile(userId)
        return { content: [{ type: 'text' as const, text: `✅ 已允許 ${profile.displayName} (${userId})` }] }
      }
      case 'list_allowed_users': {
        const access = loadAccess()
        if (access.allowFrom.length === 0) {
          return { content: [{ type: 'text' as const, text: '允許清單為空。用 add_allowed_user 新增用戶。' }] }
        }
        const lines: string[] = []
        for (const uid of access.allowFrom) {
          const profile = await lineGetProfile(uid)
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
        const sent = await lineMulticast(userIds, text)
        return { content: [{ type: 'text' as const, text: `✅ 已群發給 ${sent} 位用戶` }] }
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

// === Webhook HTTP Server ===

const profileCache = new Map<string, string>()

if (portAlreadyInUse) {
  process.stderr.write(`line-channel: port ${WEBHOOK_PORT} 已有另一個 instance 在跑，共用現有 webhook server\n`)
} else {
  Bun.serve({
    port: WEBHOOK_PORT,
    hostname: '0.0.0.0',
    async fetch(req) {
      const url = new URL(req.url)

      // Health check
      if (req.method === 'GET') {
        return new Response('LINE Channel OK')
      }

      if (req.method !== 'POST' || (url.pathname !== '/' && url.pathname !== '/webhook')) {
        return new Response('404', { status: 404 })
      }

      const body = await req.text()
      const signature = req.headers.get('x-line-signature') ?? ''

      if (!verifySignature(body, signature)) {
        return new Response('invalid signature', { status: 401 })
      }

      const payload = JSON.parse(body)

      for (const event of payload.events ?? []) {
        const userId = event.source?.userId ?? ''
        const chatId = event.source?.groupId ?? event.source?.roomId ?? userId
        const sourceType = event.source?.type ?? 'user'  // user | group | room

        // 群組訊息：只處理 @mention
        if (sourceType === 'group' || sourceType === 'room') {
          if (event.type === 'message' && event.message?.type === 'text') {
            const mention = event.message.mention
            if (!mention?.mentionees?.length) continue  // 沒 @，跳過
            // 去掉 @mention 文字
            let text = event.message.text as string
            for (const m of [...mention.mentionees].sort((a: any, b: any) => (b.index ?? 0) - (a.index ?? 0))) {
              text = text.slice(0, m.index ?? 0) + text.slice((m.index ?? 0) + (m.length ?? 0))
            }
            event.message.text = text.trim()
          } else {
            continue  // 群組中非文字或沒 @，跳過
          }
        }

        // Access control：只推送允許名單中的用戶
        const access = loadAccess()
        if (access.allowFrom.length > 0 && !access.allowFrom.includes(userId)) {
          continue  // 不在允許清單，靜默忽略
        }

        // 取得用戶暱稱（快取）
        let displayName = profileCache.get(userId)
        if (!displayName) {
          const profile = await lineGetProfile(userId)
          displayName = profile.displayName
          profileCache.set(userId, displayName)
        }

        if (event.type === 'message') {
          const msg = event.message
          let content = ''

          switch (msg.type) {
            case 'text':
              content = msg.text ?? ''
              break
            case 'image': {
              try {
                const imgPath = await downloadLineContent(String(msg.id), 'image')
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
              content = `[貼圖]`
              break
            case 'location':
              content = `[位置: ${msg.title ?? ''} ${msg.address ?? ''}]`
              break
            case 'file': {
              try {
                const filePath = await downloadLineContent(String(msg.id), 'file', (msg as any).fileName)
                content = `[檔案] ${filePath} (${(msg as any).fileName ?? '未知檔名'})`
              } catch {
                content = `[檔案: ${(msg as any).fileName ?? ''}] (下載失敗)`
              }
              break
            }
            default:
              content = `[${msg.type}]`
          }

          // 寫入 DB（不管 Claude 有沒有處理，訊息都會被記錄）
          saveMessageToDb(
            String(msg.id ?? ''), String(userId), String(displayName),
            String(sourceType), sourceType !== 'user' ? String(chatId) : null,
            'inbound', content, String(msg.type), 'queued'
          )

          // 推送進 Claude session
          process.stderr.write(`line-channel: 推送訊息 from=${displayName} content=${content.slice(0, 50)}\n`)
          mcp.notification({
            method: 'notifications/claude/channel',
            params: {
              content,
              meta: {
                chat_id: String(chatId),
                message_id: String(msg.id ?? ''),
                user: String(displayName),
                user_id: String(userId),
                source_type: String(sourceType),
                ts: new Date(event.timestamp ?? Date.now()).toISOString(),
              },
            },
          }).catch(err => {
            process.stderr.write(`line-channel: notification 失敗: ${err}\n`)
          })
        } else if (event.type === 'follow') {
          await mcp.notification({
            method: 'notifications/claude/channel',
            params: {
              content: `${displayName} 加入追蹤`,
              meta: {
                chat_id: String(userId),
                user: String(displayName),
                user_id: String(userId),
                event_type: 'follow',
              },
            },
          })
        }
      }

      return new Response('ok')
    },
  })

  process.stderr.write(`line-channel: webhook 監聽中 http://localhost:${WEBHOOK_PORT}/webhook\n`)
}

// === ngrok 固定域名 + LINE Webhook 自動設定 ===

const NGROK_DOMAIN = process.env.NGROK_DOMAIN ?? 'eddy-unmarked-lakenya.ngrok-free.dev'

async function autoSetupNgrok(): Promise<void> {
  if (portAlreadyInUse) {
    process.stderr.write(`line-channel: 跳過 ngrok（已有 instance 在處理）\n`)
    return
  }

  // 殺掉舊的 ngrok（避免 port 衝突）
  try {
    Bun.spawnSync(['pkill', '-f', 'ngrok'])
    await Bun.sleep(1000)
  } catch {}

  // 用固定域名啟動 ngrok
  process.stderr.write(`line-channel: 啟動 ngrok --domain=${NGROK_DOMAIN} → port ${WEBHOOK_PORT}\n`)
  try {
    Bun.spawn(['ngrok', 'http', String(WEBHOOK_PORT), `--domain=${NGROK_DOMAIN}`, '--log=stdout', '--log-format=json'], {
      stdout: 'ignore',
      stderr: 'ignore',
    })
    await Bun.sleep(3000)
  } catch (e) {
    process.stderr.write(`line-channel: ngrok 啟動失敗（可能未安裝）: ${e}\n`)
    return
  }

  // 固定域名，URL 永遠一樣
  const webhookEndpoint = `https://${NGROK_DOMAIN}/webhook`

  // 設定 LINE webhook（其實只需要設一次，但每次確認不虧）
  try {
    const res = await fetch('https://api.line.me/v2/bot/channel/webhook/endpoint', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${CHANNEL_ACCESS_TOKEN}`,
      },
      body: JSON.stringify({ endpoint: webhookEndpoint }),
    })
    if (res.ok) {
      process.stderr.write(`line-channel: LINE webhook = ${webhookEndpoint} ✅\n`)
    } else {
      process.stderr.write(`line-channel: LINE webhook 設定失敗: ${res.status}\n`)
    }
  } catch (e) {
    process.stderr.write(`line-channel: LINE webhook 設定失敗: ${e}\n`)
  }
}

// 非阻塞啟動
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
