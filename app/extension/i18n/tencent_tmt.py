"""
@Time    : 2025/10/28
@Author  : Pedro
@File    : tencent_tmt_translate_async.py
@Software: PyCharm
"""
import importlib
import os
import asyncio
import sys

from tencentcloud.common import credential
from tencentcloud.tmt.v20180321 import tmt_client, models
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

from app.pedro.config import get_current_settings
from app.extension.redis.redis_client import rds


async def tencent_tmt_translate(text: str, source="auto", target="en") -> str:
    """
    异步封装版：腾讯云机器翻译（TMT）
    - 自动跳过中文目标
    - 异步 Redis 缓存（7天）
    """

    settings = get_current_settings()
    # ✅ 获取凭证
    secret_id =settings.tencent.tmt.secret_id
    secret_key = settings.tencent.tmt.secret_key

    if not secret_id or not secret_key:
        raise RuntimeError("❌ 请先设置 TENCENT_SECRET_ID / TENCENT_SECRET_KEY 环境变量")

    if not text or target.startswith("zh"):
        return text

    # ✅ Redis 缓存查询
    cache_key = f"tmt:{source}->{target}:{text}"
    r = await rds.instance()
    cached = await r.get(cache_key)
    if cached:
        print(f"✅ 命中翻译缓存：{cache_key}")
        return cached.decode("utf-8")

    # ✅ 翻译调用
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _tmt_sync_translate, secret_id, secret_key, text, source, target)

        if result:
            await r.setex(cache_key, 60 * 60 * 24 * 7, result)  # 缓存7天
        return result or text
    except Exception as e:
        print(f"⚠️ 翻译失败：{e}")
        return text


def _tmt_sync_translate(secret_id, secret_key, text, source, target):
    """同步执行腾讯TMT翻译（放在线程池中调用）"""
    try:
        cred = credential.Credential(secret_id, secret_key)
        client = tmt_client.TmtClient(cred, "ap-tokyo")

        req = models.TextTranslateRequest()
        req.SourceText = text
        req.Source = source
        req.Target = target
        req.ProjectId = 0

        resp = client.TextTranslate(req)
        return resp.TargetText
    except TencentCloudSDKException as err:
        print(f"腾讯云 TMT 翻译出错: {err}")
        return None
