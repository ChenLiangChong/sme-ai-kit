# data/ 目錄結構

所有業務資料都在這個目錄下。不進 git（在 .gitignore 中排除）。

```
data/
├── business.db                  ← SQLite 企業資料庫
└── media/
    ├── line/                    ← LINE 收到的原始媒體
    │   ├── images/              ← 圖片（.jpg）
    │   │   └── {messageId}.jpg
    │   ├── files/               ← 文件（.pdf, .xlsx, .docx 等）
    │   │   └── {messageId}.pdf
    │   ├── videos/              ← 影片（.mp4）暫不處理
    │   └── audio/               ← 語音（.m4a）暫不處理
    ├── orders/                  ← 訂單附件
    │   └── {orderId}/
    ├── customers/               ← 客戶附件
    │   └── {customerId}/
    ├── tasks/                   ← 任務附件
    │   └── {taskId}/
    ├── inventory/               ← 庫存附件
    └── exports/                 ← 系統產出的報表
        └── {日期}_{報表名}.xlsx/pdf/docx
```

## 檔案流向

1. **LINE 圖片** → `media/line/images/{messageId}.jpg` → Claude Read tool 辨識
2. **LINE 文件** → `media/line/files/{messageId}.pdf` → Claude Read / office skill 處理
3. **AI 歸類後** → `add_attachment(target_type='order', target_id=123, file_path='...')`
4. **報表產出** → `media/exports/2026-04_月報.xlsx`

## 備份

`business.db` + `media/` 整個目錄一起備份。
