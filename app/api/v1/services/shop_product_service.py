# -*- coding: utf-8 -*-
"""
@Time    : 2025/10/28 19:07
@Author  : Pedro
@File    : product_collector_service.py
@Software: PyCharm
"""
import aiohttp
import asyncio
from typing import List

from app.api.v1.model.shop_product import ShopProduct
from app.extension.redis.redis_client import rds
from app.pedro.logger import logger


class ProductCollectorService:
    """商品采集服务（Pedro-Core 异步版）"""

    DUMMY_URL = "https://dummyjson.com/products"

    @classmethod
    async def fetch_and_store(cls, limit: int = 50, lang: str = "en") -> List[dict]:
        """
        异步采集 DummyJSON 商品数据并保存
        - 自动标记 Redis 状态：running / success / error
        - 异常自动记录日志（不会中断主进程）
        - 保持 Lin 风格可读性
        """
        await rds.set("product:last_update", "running")

        try:
            # 异步请求
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(f"{cls.DUMMY_URL}?limit={limit}") as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"HTTP {resp.status}: 请求失败")
                    payload = await resp.json()

            data = (payload or {}).get("products", [])
            if not data:
                raise ValueError("返回数据为空")

            products = []
            for item in data:
                item["source"] = "dummyjson"
                item["lang"] = lang
                # 异步 upsert (需你在模型中实现 async 方法)
                obj = await ShopProduct.upsert_from_external(item)
                products.append(obj.to_dict())

            await rds.set("product:last_update", "success")
            logger.info(f"✅ 成功采集 {len(products)} 个商品")
            return products

        except Exception as e:
            await rds.set("product:last_update", f"error:{e}")
            logger.error(f"❌ 商品采集失败: {e}")
            return []
