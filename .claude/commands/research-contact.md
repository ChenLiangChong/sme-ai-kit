# 社群聯絡人研究

研究目標聯絡人（律師、KOL、合作夥伴等）的公開社群內容，並存入本地資料庫。

## 使用方式

```
/research-contact [名字 或 "all"]
```

## 流程

### 研究單一聯絡人
1. `contacts_get(name)` 取得聯絡人資料和 handles
2. 依據有的 handle，逐平台研究：
   - **Threads**：用 Apify Threads scraper（如有設定）或 WebSearch 搜尋 `site:threads.net @handle`
   - **Instagram**：用 Apify IG scraper 或 WebSearch 搜尋 `site:instagram.com handle`
   - **Facebook**：用 WebSearch 搜尋 `site:facebook.com name`
3. 每個平台爬完後呼叫 `scrape_store(name, platform, profile_data, posts_data)` 存入資料庫
4. 分析聯絡人的：
   - 專業領域和定位
   - 近期關注的話題
   - 發文風格和互動模式
   - 對 AI / 法律科技的態度（如適用）
   - 最適合的合作或聯繫切入點
5. 回報分析結果

### 批次研究
1. `contacts_list()` 取得所有聯絡人
2. 對每位執行上述流程
3. 彙整回報

### 定期更新
```
/refresh-contacts [天數]
```
1. `scrape_due(days)` 找出超過 N 天未更新的聯絡人
2. 對每位重新研究
3. 更新資料庫

## 資料庫工具清單

| Tool | 用途 |
|------|------|
| `contacts_add(name, category, ...)` | 新增聯絡人（category: lawyer/kol/partner/media/other）|
| `contacts_list(category?, status?, tag?)` | 列出 / 篩選聯絡人 |
| `contacts_get(name)` | 取得完整資料 + 爬取紀錄 + 近期貼文 |
| `contacts_update(name, ...)` | 更新任意欄位 |
| `scrape_store(name, platform, profile_data, posts_data)` | 儲存爬取結果 |
| `scrape_latest(name, platform?)` | 取得最新爬取資料 |
| `scrape_posts(name, platform?, limit?)` | 查詢貼文 |
| `scrape_due(days?, category?)` | 找出需要更新的聯絡人 |

## 注意事項

- 只爬取公開可見的內容
- profile_data 和 posts_data 存為 JSON 字串
- posts_data 格式：`[{"post_id":"...", "content":"...", "posted_at":"...", "likes":0, "comments":0, "shares":0, "url":"..."}]`
- 支援的平台：threads / ig / fb / twitter / linkedin / youtube
- 聯絡人狀態：pending / contacted / responded / converted / declined
