"""
# @Time    : 2025/11/2 22:38
# @Author  : Pedro
# @File    : ws_user_notify.py
# @Software: PyCharm
"""
import json
import hashlib
from typing import Optional

from bs4 import BeautifulSoup
from markdown2 import markdown

from app.extension.i18n.i18n_exception import translate_message
from app.extension.redis.redis_client import rds
from app.extension.websocket.wss import websocket_manager


# ============================================
# 🔍 内容识别 (Text / Markdown / HTML)
# ============================================
def is_html(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False

    soup = BeautifulSoup(text, "html.parser")
    return bool(soup.find()) or any(e in text for e in ["&nbsp;", "&lt;", "&gt;", "&amp;", "&quot;"])


def normalize_content(text: str):
    """自动识别 text / markdown / html"""
    if not text:
        return None, None

    if is_html(text):
        return None, text  # 认为是 HTML

    if any(c in text for c in ["#", "*", "-", "`"]):
        return None, markdown(text)  # Markdown → HTML

    return text, None  # 普通文本


def cache_key_for(lang: str, text: str, title: Optional[str]):
    h = hashlib.sha256(f"{lang}:{title}:{text}".encode()).hexdigest()
    return f"broadcast:{lang}:{h}"


# ============================================
# 🎯 私信推送
# ============================================
async def notify_user(uid: int, event: dict, lang: Optional[str] = None):
    """推送消息给指定用户（只需 content 字段，其余自动处理）"""

    content = event.get("content")
    if not content:
        raise ValueError("content 字段不能为空")

    title = event.get("title")
    level = event.get("level", "info")

    lang = lang or event.get("lang") or "en"

    # 内容格式识别
    text, html_safe = normalize_content(content)
    content_to_translate = html_safe or text

    translated = await translate_message(content_to_translate, lang)

    payload = {
        "type": "user",
        "event": event.get("event"),
        "uid": uid,
        "level": level,
        "title": await translate_message(title, lang) if title else None,
        # "lang": lang,
        "html": translated if html_safe else False,
        "message": translated if not html_safe else False,
    }

    # 🧽 清除空字段
    payload = {k: v for k, v in payload.items() if v not in [None, ""]}

    await websocket_manager.broadcast(f"user:{uid}", payload)


# ============================================
# 📢 全局广播
# ============================================
async def notify_broadcast(event: dict, lang: Optional[str] = None):
    """推送全局广播（支持翻译/缓存/Markdown/HTML）"""

    content = event.get("content")
    if not content:
        raise ValueError("content 字段不能为空")

    title = event.get("title")
    level = event.get("level", "info")

    lang = lang or event.get("lang") or "en"

    text, html_safe = normalize_content(content)
    content_to_translate = html_safe or text

    redis = await rds.instance()
    key = cache_key_for(lang, content_to_translate, title)

    cached = await redis.get(key)

    if cached:
        payload = json.loads(cached)
    else:
        translated_title = await translate_message(title, lang) if title else None
        translated = await translate_message(content_to_translate, lang)

        payload = {
            "type": "broadcast",
            "event": "system_notice",
            "broadcast": True,
            # "lang": lang,
            "title": translated_title,
            "level": level,
            "html": translated if html_safe else False,
            "message": translated if not html_safe else False,
        }
        # 🧽 清除空字段
        payload = {k: v for k, v in payload.items() if v not in [None, ""]}

        await redis.setex(key, 86400, json.dumps(payload, ensure_ascii=False))

    await websocket_manager.broadcast_all(payload)
    return True
