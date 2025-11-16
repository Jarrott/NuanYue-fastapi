# app/extension/i18n/i18n_exception.py

import importlib
import sys

from mypy.types import AnyType

from app.extension.redis.redis_client import rds
from .tencent_tmt import tencent_tmt_translate

import json


async def detect_language(header: str, default="zh") -> str:
    """
    🎯 根据 Accept-Language 自动解析用户语言
    支持 `zh-CN,ja;q=0.9,en-US;q=0.8`
    """
    if not header:
        return default

    languages = header.split(",")
    parsed = []

    for item in languages:
        parts = item.split(";q=")
        lang = parts[0].strip().lower()
        q = float(parts[1]) if len(parts) > 1 else 1
        parsed.append((lang, q))

    parsed.sort(key=lambda x: x[1], reverse=True)
    lang = parsed[0][0].split("-")[0]

    SUPPORTED = {"zh", "en", "ja", "ko", "es", "fr"}
    return lang if lang in SUPPORTED else "en"


async def translate_message(msg: str, lang: str) -> str:
    if not msg:
        return ""

        # 读取系统默认语言
    from app.config.settings_manager import get_current_settings
    default_lang = getattr(get_current_settings().i18n, "default", "zh")

    # 如果需要翻译语言 == 系统默认语言 → 跳过翻译
    if lang[:2].lower() == default_lang[:2].lower():
        return msg

    cache_key = f"i18n:{lang}:{msg}"
    r = await rds.instance()
    cached = await r.get(cache_key)
    if cached:
        return cached

    try:
        translated = await tencent_tmt_translate(msg, source="zh", target=lang[:2])
        await r.setex(cache_key, 60 * 60 * 24 * 7, translated)
        return translated
    except Exception as e:
        print(f"⚠️ 翻译失败: {e}")
        return msg
