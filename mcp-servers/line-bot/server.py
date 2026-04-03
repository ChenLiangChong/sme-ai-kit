"""
SME-AI-Kit LINE Bot MCP Server
Fork of ~/mcp-servers/line-webhook/server.py，改用 SQLite 共享 business.db。

MCP 啟動時自動：
1. 啟動 webhook server (port 8765)
2. 啟動 ngrok 隧道
3. 用 LINE API 自動設定 webhook URL
"""
import json
import os
import sys
import time
import hashlib
import hmac
import base64
import sqlite3
import threading
import subprocess
from datetime import datetime
from pathlib import Path
import urllib.request
import urllib.error

# === 設定 ===

CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.environ.get("CHANNEL_SECRET", "")
DB_PATH = os.environ.get("SME_DB_PATH", str(Path(__file__).parent.parent.parent / "data" / "business.db"))
IMAGES_DIR = os.environ.get("SME_IMAGES_DIR", str(Path(__file__).parent.parent.parent / "data" / "images"))
WEBHOOK_PORT = int(os.environ.get("LINE_WEBHOOK_PORT", "8765"))
BOT_USER_ID = os.environ.get("LINE_BOT_USER_ID", "")  # Bot 自己的 userId，用於群組 @mention 過濾

# 全域狀態
_ngrok_url = ""
_webhook_running = False

# Profile 快取（記憶體，避免頻繁呼叫 LINE API）
_profile_cache: dict[str, dict] = {}
_profile_cache_ttl = 86400  # 24 小時


# === 資料庫 ===

def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    db.row_factory = sqlite3.Row
    return db


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _format_time(ts_ms):
    try:
        return datetime.fromtimestamp(ts_ms / 1000).strftime("%m/%d %H:%M")
    except (ValueError, OSError, TypeError):
        return ""


# === LINE API 工具 ===

def _get_profile(user_id: str) -> dict:
    """從快取或 LINE API 取得用戶 profile"""
    if user_id in _profile_cache:
        cached = _profile_cache[user_id]
        if time.time() - cached.get("_fetched_at", 0) < _profile_cache_ttl:
            return cached

    if not CHANNEL_ACCESS_TOKEN:
        return {"userId": user_id, "displayName": user_id[:8] + "..."}

    try:
        req = urllib.request.Request(
            f"https://api.line.me/v2/bot/profile/{user_id}",
            headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            profile = json.loads(resp.read().decode("utf-8"))
            profile["_fetched_at"] = time.time()
            _profile_cache[user_id] = profile
            return profile
    except Exception:
        return {"userId": user_id, "displayName": user_id[:8] + "..."}


def _download_line_content(message_id: str) -> str:
    """從 LINE Content API 下載媒體檔案（圖片/影片/語音/檔案），回傳本地路徑。"""
    os.makedirs(IMAGES_DIR, exist_ok=True)
    if not CHANNEL_ACCESS_TOKEN:
        return ""
    try:
        req = urllib.request.Request(
            f"https://api-data.line.me/v2/bot/message/{message_id}/content",
            headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            ext_map = {
                "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                "video/mp4": ".mp4", "audio/m4a": ".m4a", "audio/mp4": ".m4a",
            }
            ext = ext_map.get(content_type, ".bin")
            filepath = os.path.join(IMAGES_DIR, f"{message_id}{ext}")
            with open(filepath, "wb") as f:
                f.write(resp.read())
            return filepath
    except Exception:
        return ""


def _send_push(user_id: str, messages: list[dict]) -> tuple[bool, str]:
    """送出 push message"""
    if not CHANNEL_ACCESS_TOKEN:
        return False, "未設定 CHANNEL_ACCESS_TOKEN"

    payload = json.dumps({"to": user_id, "messages": messages}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/push",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
        return True, ""
    except urllib.error.HTTPError as e:
        return False, f"{e.code} {e.read().decode('utf-8', errors='replace')}"
    except Exception as e:
        return False, str(e)


def _send_broadcast(messages: list[dict]) -> tuple[bool, str]:
    """廣播訊息"""
    if not CHANNEL_ACCESS_TOKEN:
        return False, "未設定 CHANNEL_ACCESS_TOKEN"

    payload = json.dumps({"messages": messages}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/broadcast",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
        return True, ""
    except urllib.error.HTTPError as e:
        return False, f"{e.code} {e.read().decode('utf-8', errors='replace')}"
    except Exception as e:
        return False, str(e)


def _log_outbound(db: sqlite3.Connection, user_id: str, user_name: str, content: str, msg_type: str = "text", direction: str = "outbound"):
    """記錄發送的訊息到 DB"""
    db.execute(
        """INSERT INTO line_messages (line_message_id, user_id, user_name, direction, content, msg_type, status)
           VALUES (?, ?, ?, ?, ?, ?, 'replied')""",
        (f"sent_{_now_ms()}", user_id, user_name, direction, content, msg_type),
    )
    db.commit()


# === Webhook Server ===

def _start_webhook():
    """背景啟動 webhook HTTP server"""
    global _webhook_running
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            # 驗證 LINE 簽名
            if CHANNEL_SECRET:
                signature = self.headers.get("X-Line-Signature", "")
                expected = base64.b64encode(
                    hmac.new(CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
                ).decode()
                if signature != expected:
                    self.send_response(403)
                    self.end_headers()
                    return

            try:
                data = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                return

            db = get_db()
            try:
                for event in data.get("events", []):
                    event_type = event.get("type", "")
                    source = event.get("source", {})
                    source_type = source.get("type", "")  # "user" | "group" | "room"
                    user_id = source.get("userId", "")
                    group_id = source.get("groupId", "") or source.get("roomId", "")
                    timestamp = event.get("timestamp", 0)

                    if event_type == "message":
                        msg = event.get("message", {})
                        msg_type = msg.get("type", "")
                        msg_id = msg.get("id", "")

                        # 群組訊息：只處理 @mention bot 的，其餘忽略
                        if source_type in ("group", "room"):
                            mention = msg.get("mention", {})
                            mentionees = mention.get("mentionees", [])
                            bot_mentioned = any(
                                m.get("userId") == BOT_USER_ID or m.get("type") == "all"
                                for m in mentionees
                            )
                            if not bot_mentioned:
                                continue  # 沒 @bot，跳過
                            # 去掉 @mention 文字，保留實際指令
                            if msg_type == "text":
                                raw_text = msg.get("text", "")
                                for m in sorted(mentionees, key=lambda x: x.get("index", 0), reverse=True):
                                    idx = m.get("index", 0)
                                    length = m.get("length", 0)
                                    raw_text = raw_text[:idx] + raw_text[idx + length:]
                                msg["text"] = raw_text.strip()

                        # 需要下載媒體的類型
                        if msg_type in ("image", "video", "audio", "file"):
                            filepath = _download_line_content(msg_id)
                            type_label = {"image": "圖片", "video": "影片", "audio": "語音", "file": "檔案"}.get(msg_type, msg_type)
                            if filepath:
                                text = f"[{type_label}] {filepath}"
                            else:
                                text = f"[{type_label}] (下載失敗)"
                        elif msg_type == "text":
                            text = msg.get("text", "")
                        elif msg_type == "sticker":
                            text = f"[貼圖 {msg.get('packageId', '')}/{msg.get('stickerId', '')}]"
                        elif msg_type == "location":
                            text = f"[位置: {msg.get('title', '')} {msg.get('address', '')}]"
                        else:
                            text = f"[{msg_type}]"

                        profile = _get_profile(user_id) if user_id else {}

                        db.execute(
                            """INSERT INTO line_messages
                               (line_message_id, user_id, user_name, source_type, group_id, direction, content, msg_type, status)
                               VALUES (?, ?, ?, ?, ?, 'inbound', ?, ?, 'queued')""",
                            (msg.get("id", ""), user_id, profile.get("displayName", ""),
                             source_type, group_id or None, text, msg_type),
                        )

                    elif event_type == "follow":
                        profile = _get_profile(user_id) if user_id else {}
                        db.execute(
                            """INSERT INTO line_messages
                               (line_message_id, user_id, user_name, direction, content, msg_type, status)
                               VALUES (?, ?, ?, 'inbound', ?, 'event', 'queued')""",
                            (f"follow_{timestamp}", user_id, profile.get("displayName", ""),
                             f"[新追蹤] {profile.get('displayName', user_id)}"),
                        )

                    elif event_type == "unfollow":
                        db.execute(
                            """INSERT INTO line_messages
                               (line_message_id, user_id, user_name, direction, content, msg_type, status)
                               VALUES (?, ?, '', 'inbound', ?, 'event', 'processed')""",
                            (f"unfollow_{timestamp}", user_id, f"[取消追蹤] {user_id}"),
                        )

                db.commit()
            finally:
                db.close()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"LINE Webhook OK")

        def log_message(self, *args):
            pass

    server = HTTPServer(("0.0.0.0", WEBHOOK_PORT), Handler)
    _webhook_running = True
    server.serve_forever()


def _start_ngrok():
    """背景啟動 ngrok，取得 URL 後自動設定 LINE webhook"""
    global _ngrok_url
    try:
        subprocess.Popen(
            ["ngrok", "http", str(WEBHOOK_PORT), "--log=stdout", "--log-format=json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(3)

        try:
            req = urllib.request.Request("http://127.0.0.1:4040/api/tunnels")
            with urllib.request.urlopen(req, timeout=5) as resp:
                tunnels = json.loads(resp.read().decode("utf-8"))
                for t in tunnels.get("tunnels", []):
                    if t.get("proto") == "https":
                        _ngrok_url = t["public_url"]
                        break
        except Exception:
            pass

        if _ngrok_url:
            _set_line_webhook_url(_ngrok_url + "/")

    except FileNotFoundError:
        pass


def _set_line_webhook_url(url: str) -> bool:
    if not CHANNEL_ACCESS_TOKEN:
        return False
    try:
        payload = json.dumps({"endpoint": url}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.line.me/v2/bot/channel/webhook/endpoint",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
            },
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=10):
            return True
    except Exception:
        return False


def _auto_start():
    """MCP 啟動時自動啟動 webhook + ngrok"""
    # 檢查 port 是否已被佔用
    try:
        test_req = urllib.request.urlopen(f"http://localhost:{WEBHOOK_PORT}", timeout=1)
        test_req.close()
        global _webhook_running
        _webhook_running = True
    except Exception:
        t1 = threading.Thread(target=_start_webhook, daemon=True)
        t1.start()
        time.sleep(0.5)

    # 啟動 ngrok（如果還沒跑）
    try:
        test_req = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1)
        tunnels = json.loads(test_req.read().decode("utf-8"))
        for t in tunnels.get("tunnels", []):
            if t.get("proto") == "https":
                global _ngrok_url
                _ngrok_url = t["public_url"]
                break
    except Exception:
        t2 = threading.Thread(target=_start_ngrok, daemon=True)
        t2.start()


# === MCP 工具 ===

def run_mcp():
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("line-bot")

    _auto_start()

    @mcp.tool()
    def check_new_messages(mark_processed: bool = False) -> str:
        """檢查未處理的 LINE 訊息。用於 /loop 輪詢模式。

        Args:
            mark_processed: True 時將訊息狀態從 queued 改為 processed
        """
        db = get_db()
        try:
            messages = db.execute(
                """SELECT id, user_id, user_name, content, msg_type, created_at
                   FROM line_messages
                   WHERE direction = 'inbound' AND status = 'queued'
                   ORDER BY created_at""",
            ).fetchall()

            if not messages:
                return "沒有新的 LINE 訊息。"

            if mark_processed:
                ids = [m["id"] for m in messages]
                db.execute(
                    f"UPDATE line_messages SET status = 'processed' WHERE id IN ({','.join('?' * len(ids))})",
                    ids,
                )
                db.commit()

            lines = [f"## 💬 新訊息（{len(messages)} 則）"]
            for m in messages:
                lines.append(f"- [{m['created_at']}] **{m['user_name'] or m['user_id'][:8]}**: {m['content'][:200]}")
                lines.append(f"  user_id: `{m['user_id']}` | msg_id: {m['id']}")
            return "\n".join(lines)
        finally:
            db.close()

    @mcp.tool()
    def identify_sender(line_user_id: str) -> str:
        """辨識 LINE 訊息發送者的員工身份。

        Args:
            line_user_id: LINE User ID
        """
        db = get_db()
        try:
            emp = db.execute(
                "SELECT id, name, role, department, permissions FROM employees WHERE line_user_id = ? AND active = 1",
                (line_user_id,),
            ).fetchone()

            profile = _get_profile(line_user_id)
            line_name = profile.get("displayName", "未知")

            if emp:
                return (
                    f"## 已識別員工\n"
                    f"- 姓名：{emp['name']}（LINE 暱稱：{line_name}）\n"
                    f"- 角色：{emp['role']} | 權限：{emp['permissions']}\n"
                    f"- 部門：{emp['department'] or '未設定'}"
                )
            else:
                # 可能是客戶
                cust = db.execute(
                    "SELECT id, name, tags FROM customers WHERE line_user_id = ?",
                    (line_user_id,),
                ).fetchone()
                if cust:
                    return f"## 已識別客戶\n- 姓名：{cust['name']}（LINE 暱稱：{line_name}）\n- 標籤：{cust['tags'] or '無'}"

                return f"## 未識別身份\n- LINE 暱稱：{line_name}\n- User ID: `{line_user_id}`\n- 不在員工或客戶名冊中。"
        finally:
            db.close()

    @mcp.tool()
    def list_line_messages(limit: int = 30, unread_only: bool = False) -> str:
        """列出收到的 LINE 訊息。

        Args:
            limit: 最多顯示幾條
            unread_only: True 只顯示未處理訊息
        """
        db = get_db()
        try:
            if unread_only:
                messages = db.execute(
                    "SELECT * FROM line_messages WHERE direction = 'inbound' AND status = 'queued' ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                messages = db.execute(
                    "SELECT * FROM line_messages ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()

            if not messages:
                return "目前沒有 LINE 訊息。"

            total_unread = db.execute(
                "SELECT COUNT(*) as c FROM line_messages WHERE direction = 'inbound' AND status = 'queued'"
            ).fetchone()["c"]

            lines = [f"**LINE 訊息** | 顯示 {len(messages)} 則 | 🔴 未處理 {total_unread}\n"]
            for m in reversed(messages):
                if m["direction"] == "inbound":
                    status = {"queued": "🔴", "processed": "🟡", "replied": "✅"}.get(m["status"], "")
                    lines.append(f"{status} `{m['created_at']}` **{m['user_name'] or '?'}**: {m['content'][:200]}")
                else:
                    lines.append(f"📤 `{m['created_at']}` → {m['user_name'] or '?'}: {m['content'][:100]}")
            return "\n".join(lines)
        finally:
            db.close()

    @mcp.tool()
    def list_line_users() -> str:
        """列出所有傳過訊息的 LINE 用戶。"""
        db = get_db()
        try:
            users = db.execute(
                """SELECT user_id, user_name,
                          COUNT(*) as msg_count,
                          SUM(CASE WHEN direction='inbound' AND status='queued' THEN 1 ELSE 0 END) as unread,
                          MAX(created_at) as last_time,
                          (SELECT content FROM line_messages m2 WHERE m2.user_id = m1.user_id ORDER BY created_at DESC LIMIT 1) as last_msg
                   FROM line_messages m1
                   WHERE user_id != '__broadcast__'
                   GROUP BY user_id
                   ORDER BY last_time DESC""",
            ).fetchall()

            if not users:
                return "目前沒有任何用戶。"

            lines = [f"**LINE 用戶** | 共 {len(users)} 位\n"]
            for u in users:
                unread = f" 🔴 {u['unread']} 未讀" if u["unread"] > 0 else ""
                lines.append(
                    f"- **{u['user_name'] or u['user_id'][:8] + '...'}**{unread}\n"
                    f"  ID: `{u['user_id']}` | 訊息: {u['msg_count']} 則 | 最後: {u['last_time']}"
                )
            return "\n".join(lines)
        finally:
            db.close()

    @mcp.tool()
    def read_line_conversation(user_id: str, limit: int = 20) -> str:
        """讀取與特定用戶的完整對話紀錄。

        Args:
            user_id: 用戶 ID
            limit: 最多顯示幾條
        """
        db = get_db()
        try:
            messages = db.execute(
                "SELECT * FROM line_messages WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()

            if not messages:
                return f"找不到與 {user_id} 的對話。"

            profile = _get_profile(user_id)
            name = profile.get("displayName", user_id[:8] + "...")

            # 標記為已處理
            db.execute(
                "UPDATE line_messages SET status = 'processed' WHERE user_id = ? AND direction = 'inbound' AND status = 'queued'",
                (user_id,),
            )
            db.commit()

            lines = [f"## 與 {name} 的對話\nUser ID: `{user_id}`\n---\n"]
            for m in reversed(messages):
                if m["direction"] == "outbound":
                    lines.append(f"`{m['created_at']}` 📤 **你**: {m['content']}")
                else:
                    lines.append(f"`{m['created_at']}` 💬 **{name}**: {m['content']}")
            return "\n\n".join(lines)
        finally:
            db.close()

    @mcp.tool()
    def reply_line_message(user_id: str, text: str) -> str:
        """回覆 LINE 訊息給指定用戶。

        Args:
            user_id: 用戶 ID
            text: 回覆文字
        """
        ok, err = _send_push(user_id, [{"type": "text", "text": text}])
        if not ok:
            return f"❌ 發送失敗: {err}"

        profile = _get_profile(user_id)
        name = profile.get("displayName", user_id[:8])

        db = get_db()
        try:
            _log_outbound(db, user_id, name, text)
            # 標記該用戶最近的 queued 訊息為 replied
            db.execute(
                "UPDATE line_messages SET status = 'replied', reply_content = ? WHERE user_id = ? AND direction = 'inbound' AND status IN ('queued', 'processed')",
                (text[:200], user_id),
            )
            db.commit()
        finally:
            db.close()

        return f"✅ 已發送給 {name}: {text[:50]}"

    @mcp.tool()
    def send_line_flex(user_id: str, alt_text: str, flex_json: str) -> str:
        """發送 Flex Message（進階排版訊息）。

        Args:
            user_id: 用戶 ID
            alt_text: 替代文字
            flex_json: Flex Message JSON 內容
        """
        try:
            flex_content = json.loads(flex_json) if isinstance(flex_json, str) else flex_json
        except json.JSONDecodeError:
            return "❌ flex_json 格式錯誤"

        ok, err = _send_push(user_id, [{"type": "flex", "altText": alt_text, "contents": flex_content}])
        if not ok:
            return f"❌ 發送失敗: {err}"

        profile = _get_profile(user_id)
        db = get_db()
        try:
            _log_outbound(db, user_id, profile.get("displayName", ""), f"[Flex] {alt_text}", "flex")
        finally:
            db.close()

        return f"✅ 已發送 Flex Message 給 {profile.get('displayName', user_id)}"

    @mcp.tool()
    def broadcast_line_text(text: str) -> str:
        """廣播文字訊息給所有追蹤者。

        Args:
            text: 廣播內容
        """
        ok, err = _send_broadcast([{"type": "text", "text": text}])
        if not ok:
            return f"❌ 廣播失敗: {err}"

        db = get_db()
        try:
            _log_outbound(db, "__broadcast__", "全體追蹤者", f"[廣播] {text}", "text", "broadcast")
        finally:
            db.close()

        return f"✅ 已廣播: {text[:50]}"

    @mcp.tool()
    def broadcast_line_flex(alt_text: str, flex_json: str) -> str:
        """廣播 Flex Message 給所有追蹤者。

        Args:
            alt_text: 替代文字
            flex_json: Flex Message JSON
        """
        try:
            flex_content = json.loads(flex_json) if isinstance(flex_json, str) else flex_json
        except json.JSONDecodeError:
            return "❌ flex_json 格式錯誤"

        ok, err = _send_broadcast([{"type": "flex", "altText": alt_text, "contents": flex_content}])
        if not ok:
            return f"❌ 廣播失敗: {err}"

        db = get_db()
        try:
            _log_outbound(db, "__broadcast__", "全體追蹤者", f"[廣播 Flex] {alt_text}", "flex", "broadcast")
        finally:
            db.close()

        return f"✅ 已廣播 Flex Message: {alt_text}"

    @mcp.tool()
    def get_line_quota() -> str:
        """查詢 LINE 官方帳號的訊息額度和本月用量。"""
        if not CHANNEL_ACCESS_TOKEN:
            return "錯誤：未設定 CHANNEL_ACCESS_TOKEN"

        results = []
        headers = {"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}

        for label, url in [
            ("額度", "https://api.line.me/v2/bot/message/quota"),
            ("用量", "https://api.line.me/v2/bot/message/quota/consumption"),
        ]:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if "value" in data:
                        results.append(f"**月額度**: {data['value']}")
                    if "totalUsage" in data:
                        results.append(f"**本月已用**: {data['totalUsage']} 則")
            except Exception as e:
                results.append(f"{label}查詢失敗: {e}")

        return "## LINE 帳號狀態\n\n" + "\n".join(results)

    @mcp.tool()
    def line_webhook_status() -> str:
        """查看 LINE webhook 狀態。"""
        db = get_db()
        try:
            stats = {
                "收到": db.execute("SELECT COUNT(*) as c FROM line_messages WHERE direction='inbound'").fetchone()["c"],
                "未處理": db.execute("SELECT COUNT(*) as c FROM line_messages WHERE direction='inbound' AND status='queued'").fetchone()["c"],
                "已發送": db.execute("SELECT COUNT(*) as c FROM line_messages WHERE direction IN ('outbound','broadcast')").fetchone()["c"],
                "用戶數": db.execute("SELECT COUNT(DISTINCT user_id) as c FROM line_messages WHERE user_id != '__broadcast__'").fetchone()["c"],
            }
        finally:
            db.close()

        webhook_ok = False
        try:
            with urllib.request.urlopen(f"http://localhost:{WEBHOOK_PORT}", timeout=2):
                webhook_ok = True
        except Exception:
            pass

        return (
            f"## LINE Webhook 狀態\n\n"
            f"Webhook: {'🟢 運行中' if webhook_ok else '🔴 未啟動'} (port {WEBHOOK_PORT})\n"
            f"Ngrok: {'🟢 ' + _ngrok_url if _ngrok_url else '🔴 未連線'}\n\n"
            f"**訊息統計**\n"
            + "\n".join(f"- {k}: {v}" for k, v in stats.items())
        )

    mcp.run()


if __name__ == "__main__":
    run_mcp()
