"""
# @Time    : 2025/10/28 9:39
# @Author  : Pedro
# @File    : i18n_exception.py
# @Software: PyCharm
"""
import importlib
import sys

from app.extension.redis.redis_client import rds
from .tencent_tmt import tencent_tmt_translate

import json


async def translate_message(msg: str, lang: str) -> str:
    """翻译消息文本（Redis 缓存）"""
    # 中文不用翻译
    if lang.startswith("zh"):
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