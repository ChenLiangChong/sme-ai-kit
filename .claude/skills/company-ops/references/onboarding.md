# 新人導引專業指南

## 觸發情境

「新人報到」「加入新員工」「幫 XXX 開帳號」「有人離職」

## 權限

只有 admin 或 manager 可以操作。

---

## 一、新增員工

### 資訊收集

問清楚：
- 姓名（必填）
- 角色：staff / manager（必填）
- 部門（建議填）
- 權限：basic / manager / admin（必填，預設依角色：staff→basic, manager→manager）
- 電話（建議填）
- LINE user ID（稍後綁定）

### 執行

```
register_employee(name, role, department, permissions, phone)
```

---

## 二、LINE 綁定

### 自動綁定流程

員工加入 LINE OA 後傳「我是 XXX」：

1. Channel 收到訊息 → Claude 觸發 line-comms 流程
2. `lookup_employee(訊息中的名字)` 搜尋
3. 找到且 line_user_id 為空 → 詢問確認：「你是 {部門} 的 {名字} 嗎？」
4. 員工確認 → 用 `update_employee` 綁定 LINE ID：
   `update_employee(employee_id=員工ID, line_user_id='Uxxxx')`
5. 回覆：「綁定成功！」→ 發送歡迎訊息

### 同名處理

如果有多人同名：
- 列出所有同名員工（含部門）
- 讓員工選：「請問你是哪一位？1. 倉庫的小王 2. 門市的小王」

### 綁定失敗處理

- 名字不在員工名冊 → 走陌生人流程（通知老闆）
- 已經被別人綁過 → 「這個帳號已綁定到 {其他人}，請聯繫主管」

---

## 三、歡迎訊息

綁定成功後自動發送：

```
歡迎加入 {公司名稱}！🎉

你可以在這裡：
📝 查待辦 → 傳「我的任務」
📦 查庫存 → 傳「查庫存 + 品名」
✅ 回報進度 → 傳「#任務編號 做完了」
📊 看狀態 → 傳「今天有什麼事」

有問題隨時問我！
```

---

## 四、首週訓練任務

自動建立：
```
create_task(
  title='新人訓練 - {姓名}',
  description='完成以下項目：
1. 了解公司基本規則（問 AI「公司規定」）
2. 熟悉 LINE 常用指令
3. 完成第一次庫存查詢
4. 完成第一次任務回報
5. 閱讀部門相關 SOP',
  assignee=姓名,
  priority='normal',
  due_date=一週後
)
```

---

## 五、分階段引導

### Day 1：基礎

- [x] 帳號建立 + LINE 綁定
- [ ] 發送歡迎訊息
- [ ] 建立訓練任務
- [ ] 介紹基本 LINE 指令

### Day 2-3：熟悉

員工第一次用 LINE 問問題時，耐心引導：
- 如果問的東西在知識庫有答案 → 回答 + 「以後你可以直接問我這類問題」
- 如果問的東西沒有 → 「這個我不確定，建議問 {主管名}」

### Day 4-7：獨立

- 追蹤訓練任務進度
- 第 5 天主動問：「新人訓練還順利嗎？有沒有什麼不清楚的？」
- 第 7 天提醒主管：「{姓名} 的新人訓練任務明天到期」

---

## 六、離職處理

當老闆說「XXX 離職了」「XXX 不做了」：

### 步驟

1. **確認身份和權限**（只有 admin 可操作）
2. **列出該員工的未完成任務**：
   ```
   list_tasks(assignee=姓名, status='pending')
   list_tasks(assignee=姓名, status='in_progress')
   ```
3. **問老闆**：「{姓名} 還有 {N} 項未完成任務，要轉移給誰？」
4. **轉移任務** → 逐一 `update_task(task_id, assignee=新負責人)`
5. **停用帳號 + 解綁 LINE**：
   ```
   update_employee(
     employee_id=員工ID,
     line_user_id='',       // 清除 LINE 綁定
     permissions='none',    // 移除所有權限
     active=0,              // 標記為離職
     notes='離職日期：{日期}，原因：{原因}'
   )
   ```
6. **記錄** → `store_fact(category='hr', title='離職記錄-{姓名}', content='離職日期：{日期}，原因：{原因}，已轉移任務、解綁LINE、停用帳號')`
7. **回報完成**

### 知識轉移

如果離職的是資深員工：
- 提醒老闆：「{姓名} 可能有一些未文件化的知識，要不要在他離開前做一次訪談？」
- 如果要 → 啟動 knowledge-capture 的主動訪談流程

---

## Do's and Don'ts

### Do
- 確認操作者有 admin 或 manager 權限才執行
- 離職用 `update_employee(active=0)` 停用，不要刪除紀錄
- 所有操作記 `log_interaction`
- 新人第一週回覆更詳細耐心
- 資深員工離職前提醒老闆做知識轉移訪談

### Don't
- 不要代替老闆決定新人的角色和權限（問清楚）
- 不要刪除離職員工紀錄（用 active=0）
- 不要讓 basic 權限的人操作人事異動
- 不要跳過 LINE 綁定確認步驟

## 快速參考

### 新人報到完整流程
1. `register_employee(name='王小明', role='staff', department='倉庫', permissions='basic', phone='0912-345-678')`
2. 請新人傳訊息到 LINE OA → `lookup_employee(name_or_line_id='王小明')` → `update_employee(employee_id=ID, line_user_id='Uxxxx')`
3. `reply(channel_id='default', chat_id='Uxxxx', text='歡迎加入！')`
4. `create_task(title='新人訓練 - 王小明', assignee='王小明', due_date='一週後', category='admin')`

### 離職處理
1. `list_tasks(assignee='離職員工', status='pending')` — 查未完成任務
2. 問老闆任務轉移給誰 → 逐一 `update_task(task_id=ID, assignee='新負責人')`
3. `update_employee(employee_id=ID, line_user_id='', permissions='none', active=0, notes='離職日期...')`

---

## 七、注意事項

- 離職不刪除紀錄，用 `update_employee(active=0)` 停用，`list_employees(active_only=True)` 會自動過濾
- LINE 綁定用自然語言比對，不用綁定碼
- 所有操作記 interaction_log
- 新人第一週多包容，回覆更詳細
