# -*- coding: utf-8 -*-
"""
@Time    : 2025/11/10 14:01
@Author  : Pedro
@File    : product_collector_service.py
@Software: PyCharm
"""
import aiohttp
import asyncio
import random
from decimal import Decimal
from typing import List, Dict, Any

from app.api.v1.model.shop_product import ShopProduct
from app.extension.redis.redis_client import rds
from app.pedro.logger import logger


# ==========================================================
# 🧮 辅助函数：统一数值转换
# ==========================================================
def _to_decimal(val) -> Decimal:
    try:
        if val is None:
            return Decimal("0")
        return Decimal(str(val))
    except Exception:
        return Decimal("0")


class ProductCollectorService:
    """🛍️ 商品采集服务（DummyJSON v2 全字段版 + 自动利润计算）"""

    DUMMY_URL = "https://dummyjson.com/products"
    CONCURRENCY = 20

    # ----------------------------------------
    # 主采集入口
    # ----------------------------------------
    @classmethod
    async def fetch_and_store(cls, limit: int = 50, lang: str = "en") -> List[Dict[str, Any]]:
        await rds.set("product:last_update", "running")
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(f"{cls.DUMMY_URL}?limit={limit}") as resp:
                    payload = await resp.json()

            data = cls._normalize_data(payload)
            if not data:
                raise ValueError("返回数据为空")

            products = await cls._bulk_save(data, lang)
            await rds.set("product:last_update", "success")
            logger.info(f"✅ 成功采集 {len(products)} 个商品")
            return products

        except Exception as e:
            await rds.set("product:last_update", f"error:{e}")
            logger.error(f"❌ 商品采集失败: {e}")
            return []

    # ----------------------------------------
    # 数据标准化（提取价格 / 图片 / 评论）
    # ----------------------------------------
    @classmethod
    def _normalize_data(cls, payload: dict) -> List[Dict[str, Any]]:
        products = []
        for p in payload.get("products", []):
            try:
                meta = p.get("meta", {}) or {}
                dimensions = p.get("dimensions", {}) or {}
                reviews = p.get("reviews", [])
                price_raw = p.get("price")

                item = {
                    "id": p.get("id"),
                    "title": p.get("title"),
                    "description": p.get("description"),
                    "brand": p.get("brand") or "Unknown",
                    "category": p.get("category") or "Uncategorized",
                    "price": float(price_raw) if price_raw else 0.0,
                    "discount": float(p.get("discountPercentage") or 0.0),
                    "rating": float(p.get("rating") or 0.0),
                    "stock": int(p.get("stock") or 0),
                    "thumbnail": p.get("thumbnail"),
                    "images": p.get("images", []),
                    "tags": ", ".join(p.get("tags", [])),
                    "barcode": meta.get("barcode"),
                    "qr_code": meta.get("qrCode"),
                    "warranty": p.get("warrantyInformation"),
                    "shipping": p.get("shippingInformation"),
                    "return_policy": p.get("returnPolicy"),
                    "min_order_qty": int(p.get("minimumOrderQuantity", 1)),
                    "width": float(dimensions.get("width") or 0),
                    "height": float(dimensions.get("height") or 0),
                    "depth": float(dimensions.get("depth") or 0),
                    "created_at": meta.get("createdAt"),
                    "updated_at": meta.get("updatedAt"),
                    "reviews": [
                        {
                            "rating": r.get("rating"),
                            "comment": r.get("comment"),
                            "reviewer": r.get("reviewerName"),
                            "date": r.get("date")
                        }
                        for r in reviews
                    ],
                }

                # ✅ 校验打印：确认采集字段完整
                logger.info(f"[CHECK] {item['title']} | price={item['price']} | images={len(item['images'])} | reviews={len(item['reviews'])}")

                products.append(item)

            except Exception as e:
                logger.warning(f"[WARN] 跳过异常商品: {p.get('title')} | {e}")
                continue

        return products

    # ----------------------------------------
    # 并发保存
    # ----------------------------------------
    @classmethod
    async def _bulk_save(cls, items: List[Dict[str, Any]], lang: str):
        sem = asyncio.Semaphore(cls.CONCURRENCY)

        async def _task(item):
            async with sem:
                return await cls._save_product(item, lang)

        results = await asyncio.gather(*[_task(it) for it in items], return_exceptions=True)
        return [r for r in results if isinstance(r, dict)]

    # ----------------------------------------
    # 保存 + 利润计算
    # ----------------------------------------
    @classmethod
    async def _save_product(cls, item: dict, lang: str):
        try:
            retail_price = _to_decimal(item.get("price"))
            cost_price = (retail_price * Decimal("0.8")).quantize(Decimal("0.01"))
            sale_price = (cost_price * Decimal("1.1")).quantize(Decimal("0.01"))
            profit_amount = (retail_price - cost_price).quantize(Decimal("0.01"))
            stock_dec = _to_decimal(item.get("stock"))
            expected_profit = (profit_amount * stock_dec).quantize(Decimal("0.01"))

            payload = {
                "id": item.get("id") or random.randint(100000, 999999),
                "title": item.get("title"),
                "description": item.get("description"),
                "brand": item.get("brand"),
                "category": item.get("category"),
                "stock": item.get("stock"),
                "retail_price": float(retail_price),
                "cost_price": float(cost_price),
                "sale_price": float(sale_price),
                "profit_amount": float(profit_amount),
                "expected_profit": float(expected_profit),
                "image": item.get("thumbnail"),
                "images": item.get("images"),
                "tags": item.get("tags"),
                "rating": item.get("rating"),
                "barcode": item.get("barcode"),
                "shipping": item.get("shipping"),
                "warranty": item.get("warranty"),
                "return_policy": item.get("return_policy"),
                "min_order_qty": item.get("min_order_qty"),
                "reviews": item.get("reviews"),
                "lang": lang,
                "source": "dummyjson",
            }

            obj = await ShopProduct.upsert_from_external(payload)
            return obj.to_dict()

        except Exception as e:
            logger.error(f"❌ 保存商品失败: {item.get('title')} | {e}")
            return {}

