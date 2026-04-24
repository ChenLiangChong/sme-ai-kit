#!/usr/bin/env bun
/**
 * html_to_pptx.mjs — HTML → PPTX（screenshot 版）
 *
 * 把 HTML 頁面用 Playwright headless chromium 截圖，再用 pptxgenjs 包成 .pptx。
 * 每張截圖佔滿一張 16:9 投影片（full-bleed）。
 *
 * 使用方式：
 *   bun run html_to_pptx.mjs --input report.html --output report.pptx
 *   bun run html_to_pptx.mjs --input deck.html --output deck.pptx --selector "[data-slide]"
 *   bun run html_to_pptx.mjs --input deck.html --output deck.pptx --width 1920 --height 1080
 *
 * 選項：
 *   --input     <path>   輸入 HTML 檔路徑（必填）
 *   --output    <path>   輸出 PPTX 檔路徑（必填）
 *   --selector  <css>    每個 matched 元素截一張（不帶則整頁截一張）
 *   --width     <px>     viewport 寬（預設 1920）
 *   --height    <px>     viewport 高（預設 1080）
 *   --help, -h           顯示用法
 *
 * 前置安裝：
 *   cd .claude/skills/sme-design && bun install
 *   bunx playwright install chromium
 */

import { pathToFileURL } from 'node:url'
import { resolve, isAbsolute, dirname } from 'node:path'
import { statSync, existsSync } from 'node:fs'
import { mkdir } from 'node:fs/promises'

// 依賴在 main() 中才載入，讓 --help 在沒裝依賴時仍可顯示

// ─────────────────────────────────────────────────────────────
// CLI 參數解析
// ─────────────────────────────────────────────────────────────
function parseArgs(argv) {
  const args = {
    input: null,
    output: null,
    selector: null,
    width: 1920,
    height: 1080,
    help: false,
  }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    const next = () => argv[++i]
    switch (a) {
      case '-h':
      case '--help':
        args.help = true
        break
      case '--input':
        args.input = next()
        break
      case '--output':
        args.output = next()
        break
      case '--selector':
        args.selector = next()
        break
      case '--width':
        args.width = parseInt(next(), 10)
        break
      case '--height':
        args.height = parseInt(next(), 10)
        break
      default:
        // 未知參數：丟錯避免靜默吃掉
        throw new Error(`未知參數：${a}`)
    }
  }
  return args
}

function printHelp() {
  console.log(`html_to_pptx — HTML → PPTX（screenshot 版）

用法：
  bun run html_to_pptx.mjs --input <html> --output <pptx> [選項]

必填：
  --input    <path>   輸入 HTML 檔
  --output   <path>   輸出 PPTX 檔

選項：
  --selector <css>    每個 matched 元素截一張（例：[data-slide]）
  --width    <px>     viewport 寬（預設 1920）
  --height   <px>     viewport 高（預設 1080）
  --help, -h          顯示此說明

例子：
  bun run html_to_pptx.mjs --input report.html --output report.pptx
  bun run html_to_pptx.mjs --input deck.html --output deck.pptx --selector "[data-slide]"
`)
}

// ─────────────────────────────────────────────────────────────
// 主流程
// ─────────────────────────────────────────────────────────────
async function main() {
  const argv = process.argv.slice(2)
  let args
  try {
    args = parseArgs(argv)
  } catch (e) {
    console.error(e.message)
    printHelp()
    process.exit(1)
  }

  if (args.help || argv.length === 0) {
    printHelp()
    process.exit(args.help ? 0 : 1)
  }

  if (!args.input || !args.output) {
    console.error('錯誤：--input 和 --output 為必填')
    printHelp()
    process.exit(1)
  }

  // 解析完參數再載入重量級依賴
  let playwright, PptxGenJS
  try {
    playwright = await import('playwright')
  } catch (e) {
    const msg = e?.message ?? String(e)
    console.error('缺少 playwright。請執行：')
    console.error('  cd .claude/skills/sme-design && bun install')
    if (/chromium|browser|executable/i.test(msg)) {
      console.error('  bunx playwright install chromium')
    }
    console.error('')
    console.error('原始錯誤：', msg)
    process.exit(1)
  }
  try {
    const pptxMod = await import('pptxgenjs')
    PptxGenJS = pptxMod.default ?? pptxMod
  } catch (e) {
    console.error('缺少 pptxgenjs。請執行：')
    console.error('  cd .claude/skills/sme-design && bun install')
    console.error('')
    console.error('原始錯誤：', e?.message ?? e)
    process.exit(1)
  }

  const inputPath = isAbsolute(args.input) ? args.input : resolve(process.cwd(), args.input)
  const outputPath = isAbsolute(args.output) ? args.output : resolve(process.cwd(), args.output)

  if (!existsSync(inputPath)) {
    console.error(`錯誤：找不到輸入檔 ${inputPath}`)
    process.exit(1)
  }

  if (!Number.isFinite(args.width) || !Number.isFinite(args.height) || args.width <= 0 || args.height <= 0) {
    console.error('錯誤：--width / --height 必須是正整數')
    process.exit(1)
  }

  const t0 = Date.now()
  const { chromium } = playwright

  const browser = await chromium.launch({ headless: true })
  let screenshots = []
  try {
    const context = await browser.newContext({
      viewport: { width: args.width, height: args.height },
      deviceScaleFactor: 1,
    })
    const page = await context.newPage()

    // ── 可觀測性：把瀏覽器端的錯誤/請求失敗/console error 浮到 stdout
    page.on('pageerror', (err) => {
      console.error('[page error]', err?.message ?? err)
    })
    page.on('requestfailed', (req) => {
      const why = req.failure()?.errorText ?? 'unknown'
      console.warn('[request failed]', req.url(), why)
    })
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        console.error('[console error]', msg.text())
      } else if (msg.type() === 'warning') {
        console.warn('[console warn]', msg.text())
      }
    })

    const fileUrl = pathToFileURL(inputPath).href
    await page.goto(fileUrl, { waitUntil: 'networkidle' })

    // 等字型載入完成（常見 bug：沒等就截會抓到 fallback 字型）
    await page.waitForFunction(() => document.fonts && document.fonts.status === 'loaded').catch(async () => {
      // 舊瀏覽器可能沒有 status，退而等 ready
      await page.evaluate(() => document.fonts?.ready)
    })

    // 保險延遲：等動畫/漸變
    await page.waitForTimeout(500)

    if (args.selector) {
      const handles = await page.$$(args.selector)
      if (handles.length === 0) {
        throw new Error(`selector "${args.selector}" 沒有 match 到任何元素`)
      }
      for (const h of handles) {
        // scrollIntoView 確保元素在 viewport 內，lazy-load 的圖/字型才會被觸發
        await h.evaluate((el) => el.scrollIntoViewIfNeeded?.() ?? el.scrollIntoView())
        await page.waitForTimeout(100)
        const buf = await h.screenshot({ type: 'png' })
        screenshots.push(buf)
      }
    } else {
      // 整個 viewport 截一張
      const buf = await page.screenshot({ type: 'png', fullPage: false })
      screenshots.push(buf)
    }

    // Overflow 檢查：若 document 寬/高 > viewport，警告（screenshot 版本會裁掉多的）
    const overflow = await page.evaluate(({ vw, vh }) => ({
      scrollWidth: document.documentElement.scrollWidth,
      scrollHeight: document.documentElement.scrollHeight,
      vw, vh,
    }), { vw: args.width, vh: args.height })
    if (overflow.scrollWidth > overflow.vw + 1) {
      console.warn(`[overflow] document 寬 ${overflow.scrollWidth}px > viewport ${overflow.vw}px — 截圖內容可能溢出右側，右邊會被裁掉`)
    }
    if (overflow.scrollHeight > overflow.vh + 1) {
      console.warn(`[overflow] document 高 ${overflow.scrollHeight}px > viewport ${overflow.vh}px — 截圖內容可能溢出底部，下方會被裁掉`)
    }
  } finally {
    await browser.close()
  }

  // ─────────────────────────────────────────────────────────────
  // 產生 PPTX
  // ─────────────────────────────────────────────────────────────
  const pptx = new PptxGenJS()
  // 16:9 預設尺寸（pptxgenjs LAYOUT_WIDE = 13.333 x 7.5 吋）
  pptx.layout = 'LAYOUT_WIDE'
  const SLIDE_W = 13.333
  const SLIDE_H = 7.5

  for (const buf of screenshots) {
    const slide = pptx.addSlide()
    // full-bleed：從 (0,0) 鋪滿整張 slide
    slide.addImage({
      data: `data:image/png;base64,${buf.toString('base64')}`,
      x: 0,
      y: 0,
      w: SLIDE_W,
      h: SLIDE_H,
      sizing: { type: 'cover', w: SLIDE_W, h: SLIDE_H },
    })
  }

  // 輸出目錄不存在就自動建
  await mkdir(dirname(outputPath), { recursive: true })

  await pptx.writeFile({ fileName: outputPath })

  const elapsed = ((Date.now() - t0) / 1000).toFixed(2)
  let size = '?'
  try {
    size = `${(statSync(outputPath).size / 1024).toFixed(1)} KB`
  } catch {
    // ignore
  }
  console.log(`完成：${screenshots.length} 張投影片 → ${outputPath}（${size}，耗時 ${elapsed}s）`)
}

// 頂層錯誤：不吞掉
main().catch((err) => {
  console.error('失敗：', err?.stack ?? err?.message ?? err)
  process.exit(1)
})
