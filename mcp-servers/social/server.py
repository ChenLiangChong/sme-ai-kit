"""
SME-AI-Kit Social Media MCP Server
跨平台社群媒體管理（Facebook、Instagram、Threads）。
搬自 lawyerSupport/social-mcp-server.py，發文類功能暫時停用。
"""
import os
import json
import time
import requests
from typing import Any, Optional
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("social")

# ── Config ──────────────────────────────────────────────
FB_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
FB_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "")
FB_API = "https://graph.facebook.com/v25.0"

IG_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", FB_TOKEN)
IG_ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
IG_API = "https://graph.facebook.com/v25.0"

THREADS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN", "")
THREADS_API = "https://graph.threads.net/v1.0"


# ── Helpers ─────────────────────────────────────────────
def _fb_request(method, endpoint, params=None, json_data=None):
    params = params or {}
    params["access_token"] = FB_TOKEN
    url = f"{FB_API}/{endpoint}"
    r = requests.request(method, url, params=params, json=json_data)
    return r.json()

def _ig_request(method, endpoint, params=None, json_data=None):
    params = params or {}
    params["access_token"] = IG_TOKEN
    url = f"{IG_API}/{endpoint}"
    r = requests.request(method, url, params=params, json=json_data)
    return r.json()

def _threads_request(method, endpoint, params=None):
    params = params or {}
    params["access_token"] = THREADS_TOKEN
    url = f"{THREADS_API}/{endpoint}"
    r = requests.request(method, url, params=params)
    return r.json()


# ═══════════════════════════════════════════════════════
#  跨平台整合工具（蒐集類）
# ═══════════════════════════════════════════════════════

@mcp.tool()
def get_all_profiles() -> dict:
    """一次取得 Facebook、Instagram、Threads 三個平台的個人資料。"""
    result = {}
    try:
        result["facebook"] = _fb_request("GET", FB_PAGE_ID, {
            "fields": "id,name,about,description,website,phone,emails,category,fan_count,followers_count,cover,picture"
        })
    except Exception as e:
        result["facebook"] = {"error": str(e)}
    try:
        result["instagram"] = _ig_request("GET", IG_ACCOUNT_ID, {
            "fields": "id,username,name,biography,website,profile_picture_url,followers_count,follows_count,media_count"
        })
    except Exception as e:
        result["instagram"] = {"error": str(e)}
    try:
        result["threads"] = _threads_request("GET", "me", {
            "fields": "id,username,name,threads_profile_picture_url,threads_biography"
        })
    except Exception as e:
        result["threads"] = {"error": str(e)}
    return result


@mcp.tool()
def get_all_posts() -> dict:
    """一次取得 Facebook、Instagram、Threads 三個平台的最新貼文。"""
    result = {}
    try:
        result["facebook"] = _fb_request("GET", f"{FB_PAGE_ID}/posts", {
            "fields": "id,message,created_time,full_picture,permalink_url"
        })
    except Exception as e:
        result["facebook"] = {"error": str(e)}
    try:
        result["instagram"] = _ig_request("GET", f"{IG_ACCOUNT_ID}/media", {
            "fields": "id,media_type,media_url,permalink,caption,timestamp,like_count,comments_count",
            "limit": "25"
        })
    except Exception as e:
        result["instagram"] = {"error": str(e)}
    try:
        result["threads"] = _threads_request("GET", "me/threads", {
            "fields": "id,text,timestamp,media_type,shortcode,permalink,is_quote_post"
        })
    except Exception as e:
        result["threads"] = {"error": str(e)}
    return result


# ═══════════════════════════════════════════════════════
#  跨平台發文（暫時停用 — 需要 HITL 審核機制後再啟用）
# ═══════════════════════════════════════════════════════

# @mcp.tool()
# def cross_post(message: str, platforms: str = "fb,ig,threads") -> dict:
#     """同時發文到多個平台。platforms 用逗號分隔，可選: fb, ig, threads。
#     注意：IG 需要圖片才能發文，純文字只會發到 FB 和 Threads。"""
#     targets = [p.strip().lower() for p in platforms.split(",")]
#     result = {}
#     if "fb" in targets:
#         try: result["facebook"] = _fb_request("POST", f"{FB_PAGE_ID}/feed", {"message": message})
#         except Exception as e: result["facebook"] = {"error": str(e)}
#     if "threads" in targets:
#         try:
#             container = _threads_request("POST", "me/threads", {"media_type": "TEXT", "text": message})
#             container_id = container.get("id")
#             if container_id:
#                 time.sleep(2)
#                 result["threads"] = _threads_request("POST", "me/threads_publish", {"creation_id": container_id})
#             else: result["threads"] = container
#         except Exception as e: result["threads"] = {"error": str(e)}
#     if "ig" in targets:
#         result["instagram"] = {"skipped": "IG 需要圖片，請改用 cross_post_image"}
#     return result

# @mcp.tool()
# def cross_post_image(image_url: str, caption: str, platforms: str = "fb,ig,threads") -> dict:
#     """同時發圖片貼文到多個平台。"""
#     # ... 完整實作保留在原始碼中，取消註解即可啟用


# ═══════════════════════════════════════════════════════
#  Facebook 工具
# ═══════════════════════════════════════════════════════

@mcp.tool()
def fb_get_page_info() -> dict:
    """取得 Facebook 粉絲專頁資料。"""
    return _fb_request("GET", FB_PAGE_ID, {
        "fields": "id,name,about,description,website,phone,emails,category,fan_count,followers_count,cover,picture"
    })

@mcp.tool()
def fb_get_posts() -> dict:
    """取得 Facebook 粉絲專頁最新貼文。"""
    return _fb_request("GET", f"{FB_PAGE_ID}/posts", {
        "fields": "id,message,created_time,full_picture,permalink_url"
    })

# --- 發文類（暫時停用）---

# @mcp.tool()
# def fb_post(message: str) -> dict:
#     """在 Facebook 粉絲專頁發文。"""
#     return _fb_request("POST", f"{FB_PAGE_ID}/feed", {"message": message})

# @mcp.tool()
# def fb_post_image(image_url: str, caption: str) -> dict:
#     """在 Facebook 粉絲專頁發圖片貼文。"""
#     return _fb_request("POST", f"{FB_PAGE_ID}/photos", {"url": image_url, "caption": caption})

# @mcp.tool()
# def fb_schedule_post(message: str, publish_time: int) -> dict:
#     """排程 Facebook 貼文。publish_time 為 Unix timestamp。"""
#     return _fb_request("POST", f"{FB_PAGE_ID}/feed", {
#         "message": message, "published": "false", "scheduled_publish_time": str(publish_time)
#     })

# @mcp.tool()
# def fb_update_post(post_id: str, new_message: str) -> dict:
#     """更新 Facebook 貼文內容。"""
#     return _fb_request("POST", post_id, {"message": new_message})

# @mcp.tool()
# def fb_delete_post(post_id: str) -> dict:
#     """刪除 Facebook 貼文。"""
#     return _fb_request("DELETE", post_id)

# --- 留言 & 數據（啟用）---

@mcp.tool()
def fb_get_comments(post_id: str) -> dict:
    """取得 Facebook 貼文的留言。"""
    return _fb_request("GET", f"{post_id}/comments", {"fields": "id,message,from,created_time"})

# @mcp.tool()
# def fb_reply_comment(comment_id: str, message: str) -> dict:
#     """回覆 Facebook 留言。"""
#     return _fb_request("POST", f"{comment_id}/comments", {"message": message})

# @mcp.tool()
# def fb_delete_comment(comment_id: str) -> dict:
#     """刪除 Facebook 留言。"""
#     return _fb_request("DELETE", comment_id)

# @mcp.tool()
# def fb_hide_comment(comment_id: str) -> dict:
#     """隱藏 Facebook 留言。"""
#     return _fb_request("POST", comment_id, {"is_hidden": "true"})

# @mcp.tool()
# def fb_unhide_comment(comment_id: str) -> dict:
#     """取消隱藏 Facebook 留言。"""
#     return _fb_request("POST", comment_id, {"is_hidden": "false"})

@mcp.tool()
def fb_get_likes(post_id: str) -> dict:
    """取得貼文按讚數。"""
    data = _fb_request("GET", post_id, {"fields": "likes.summary(true)"})
    return {"count": data.get("likes", {}).get("summary", {}).get("total_count", 0)}

@mcp.tool()
def fb_get_shares(post_id: str) -> dict:
    """取得貼文分享數。"""
    data = _fb_request("GET", post_id, {"fields": "shares"})
    return {"count": data.get("shares", {}).get("count", 0)}

@mcp.tool()
def fb_get_fan_count() -> dict:
    """取得粉絲專頁粉絲數。"""
    data = _fb_request("GET", FB_PAGE_ID, {"fields": "fan_count"})
    return {"fan_count": data.get("fan_count", 0)}

# @mcp.tool()
# def fb_send_dm(user_id: str, message: str) -> dict:
#     """透過 Messenger 發送私訊。"""
#     payload = {"recipient": {"id": user_id}, "message": {"text": message}, "messaging_type": "RESPONSE"}
#     return _fb_request("POST", "me/messages", {}, json_data=payload)


# ═══════════════════════════════════════════════════════
#  Instagram 工具
# ═══════════════════════════════════════════════════════

@mcp.tool()
def ig_get_profile() -> dict:
    """取得 Instagram 商業帳號資料。"""
    return _ig_request("GET", IG_ACCOUNT_ID, {
        "fields": "id,username,name,biography,website,profile_picture_url,followers_count,follows_count,media_count"
    })

@mcp.tool()
def ig_get_posts(limit: int = 25) -> dict:
    """取得 Instagram 最新貼文。"""
    return _ig_request("GET", f"{IG_ACCOUNT_ID}/media", {
        "fields": "id,media_type,media_url,permalink,thumbnail_url,caption,timestamp,like_count,comments_count",
        "limit": str(min(limit, 100))
    })

@mcp.tool()
def ig_get_insights() -> dict:
    """取得 Instagram 帳號洞察報告（觸及、檔案瀏覽、網站點按）。"""
    return _ig_request("GET", f"{IG_ACCOUNT_ID}/insights", {
        "metric": "reach,profile_views,website_clicks",
        "period": "day",
        "metric_type": "total_value"
    })

@mcp.tool()
def ig_get_post_insights(media_id: str) -> dict:
    """取得 Instagram 單篇貼文的洞察數據。"""
    return _ig_request("GET", f"{media_id}/insights", {
        "metric": "reach,likes,comments,shares,saved"
    })

# --- 發文類（暫時停用）---

# @mcp.tool()
# def ig_publish_image(image_url: str, caption: str = "") -> dict:
#     """發布圖片到 Instagram。"""
#     container = _ig_request("POST", f"{IG_ACCOUNT_ID}/media", {"image_url": image_url, "caption": caption})
#     container_id = container.get("id")
#     if not container_id: return container
#     time.sleep(5)
#     return _ig_request("POST", f"{IG_ACCOUNT_ID}/media_publish", {"creation_id": container_id})

# @mcp.tool()
# def ig_publish_reel(video_url: str, caption: str = "") -> dict:
#     """發布 Reel 到 Instagram。"""
#     container = _ig_request("POST", f"{IG_ACCOUNT_ID}/media", {"video_url": video_url, "caption": caption, "media_type": "REELS"})
#     container_id = container.get("id")
#     if not container_id: return container
#     time.sleep(10)
#     return _ig_request("POST", f"{IG_ACCOUNT_ID}/media_publish", {"creation_id": container_id})

# @mcp.tool()
# def ig_publish_story(image_url: str = "", video_url: str = "") -> dict:
#     """發布限時動態到 Instagram。"""
#     params = {"media_type": "STORIES"}
#     if image_url: params["image_url"] = image_url
#     elif video_url: params["video_url"] = video_url
#     else: return {"error": "需要提供 image_url 或 video_url"}
#     container = _ig_request("POST", f"{IG_ACCOUNT_ID}/media", params)
#     container_id = container.get("id")
#     if not container_id: return container
#     time.sleep(5)
#     return _ig_request("POST", f"{IG_ACCOUNT_ID}/media_publish", {"creation_id": container_id})

# --- 留言 & DM（啟用）---

@mcp.tool()
def ig_get_comments(media_id: str, limit: int = 50) -> dict:
    """取得 Instagram 貼文的留言。"""
    return _ig_request("GET", f"{media_id}/comments", {
        "fields": "id,text,username,timestamp,like_count,replies{id,text,username,timestamp}",
        "limit": str(min(limit, 100))
    })

# @mcp.tool()
# def ig_reply_comment(comment_id: str, message: str) -> dict:
#     """回覆 Instagram 留言。"""
#     return _ig_request("POST", f"{comment_id}/replies", {"message": message})

# @mcp.tool()
# def ig_delete_comment(comment_id: str) -> dict:
#     """刪除 Instagram 留言。"""
#     return _ig_request("DELETE", comment_id)

# @mcp.tool()
# def ig_hide_comment(comment_id: str) -> dict:
#     """隱藏 Instagram 留言。"""
#     return _ig_request("POST", comment_id, {"hide": "true"})

@mcp.tool()
def ig_get_conversations(limit: int = 25) -> dict:
    """取得 Instagram DM 對話列表。"""
    return _fb_request("GET", f"{FB_PAGE_ID}/conversations", {
        "platform": "instagram",
        "fields": "id,updated_time,message_count",
        "limit": str(min(limit, 100))
    })

@mcp.tool()
def ig_get_messages(conversation_id: str, limit: int = 25) -> dict:
    """取得 Instagram DM 對話中的訊息。"""
    return _fb_request("GET", conversation_id, {
        "fields": "messages{id,from,to,message,created_time}",
        "limit": str(min(limit, 100))
    })

# @mcp.tool()
# def ig_send_dm(recipient_id: str, message: str) -> dict:
#     """發送 Instagram 私訊。"""
#     payload = {"recipient": {"id": recipient_id}, "message": {"text": message}}
#     return _fb_request("POST", "me/messages", {}, json_data=payload)


# ═══════════════════════════════════════════════════════
#  Threads 工具
# ═══════════════════════════════════════════════════════

@mcp.tool()
def threads_get_profile() -> dict:
    """取得 Threads 個人資料。"""
    return _threads_request("GET", "me", {
        "fields": "id,username,name,threads_profile_picture_url,threads_biography"
    })

@mcp.tool()
def threads_get_posts() -> dict:
    """取得 Threads 最新貼文。"""
    return _threads_request("GET", "me/threads", {
        "fields": "id,text,timestamp,media_type,shortcode,permalink,is_quote_post"
    })

# --- 發文類（暫時停用）---

# @mcp.tool()
# def threads_post(text: str) -> dict:
#     """在 Threads 發文（純文字）。"""
#     container = _threads_request("POST", "me/threads", {"media_type": "TEXT", "text": text})
#     container_id = container.get("id")
#     if not container_id: return container
#     time.sleep(2)
#     return _threads_request("POST", "me/threads_publish", {"creation_id": container_id})

# @mcp.tool()
# def threads_post_image(image_url: str, text: str = "") -> dict:
#     """在 Threads 發圖片貼文。"""
#     params = {"media_type": "IMAGE", "image_url": image_url}
#     if text: params["text"] = text
#     container = _threads_request("POST", "me/threads", params)
#     container_id = container.get("id")
#     if not container_id: return container
#     time.sleep(2)
#     return _threads_request("POST", "me/threads_publish", {"creation_id": container_id})

# --- 留言 & 數據（啟用）---

@mcp.tool()
def threads_get_replies(thread_id: str) -> dict:
    """取得 Threads 貼文的回覆。"""
    return _threads_request("GET", f"{thread_id}/replies", {
        "fields": "id,text,username,timestamp"
    })

# @mcp.tool()
# def threads_reply(reply_to_id: str, text: str) -> dict:
#     """回覆 Threads 貼文。"""
#     container = _threads_request("POST", "me/threads", {"media_type": "TEXT", "text": text, "reply_to_id": reply_to_id})
#     container_id = container.get("id")
#     if not container_id: return container
#     time.sleep(2)
#     return _threads_request("POST", "me/threads_publish", {"creation_id": container_id})

@mcp.tool()
def threads_get_insights(thread_id: str) -> dict:
    """取得 Threads 單篇貼文的洞察數據。"""
    return _threads_request("GET", f"{thread_id}/insights", {
        "metric": "views,likes,replies,reposts,quotes"
    })


if __name__ == "__main__":
    mcp.run(transport="stdio")
