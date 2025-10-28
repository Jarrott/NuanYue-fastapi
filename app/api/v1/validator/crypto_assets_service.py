"""
# @Time    : 2025/10/28 21:45
# @Author  : Pedro
# @File    : crypto_assets_service.py
# @Software: FastAPI
"""
import aiohttp
import asyncio
import logging
from app.api.v1.model.crypto_assets import CryptoAsset

logger = logging.getLogger(__name__)


class CryptoCollectorService:
    """虚拟货币采集服务（含热门榜与趋势榜）"""

    MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
    TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"

    # ======================================================
    # 📊 通用异步请求封装
    # ======================================================
    @classmethod
    async def _fetch_json(cls, url: str, params: dict | None = None) -> list | dict:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"❌ 请求失败: {resp.status} {text}")
                    raise RuntimeError(f"请求失败: {resp.status}")
                return await resp.json()

    # ======================================================
    # 🔥 市场热门币采集
    # ======================================================
    @classmethod
    async def fetch_markets(cls, vs_currency: str = "usd", limit: int = 100):
        params = {
            "vs_currency": vs_currency,
            "order": "market_cap_desc",
            "per_page": limit,
            "page": 1,
            "sparkline": "true",
            "price_change_percentage": "24h"
        }
        data = await cls._fetch_json(cls.MARKETS_URL, params)
        logger.info(f"📊 市场热门采集: 共 {len(data)} 条")
        return data

    # ======================================================
    # 📈 趋势币（热门搜索榜）
    # ======================================================
    @classmethod
    async def fetch_trending(cls):
        data = await cls._fetch_json(cls.TRENDING_URL)
        trending_ids = [coin["item"]["id"] for coin in data.get("coins", [])]
        logger.info(f"📈 趋势榜采集: {len(trending_ids)} 个币")
        return trending_ids

    # ======================================================
    # 🚀 综合采集并写入数据库
    # ======================================================
    @classmethod
    async def fetch_and_store(cls, vs_currency="usd", limit=100):
        try:
            markets, trending_ids = await asyncio.gather(
                cls.fetch_markets(vs_currency, limit),
                cls.fetch_trending()
            )
        except Exception as e:
            logger.exception(f"❌ 采集失败: {e}")
            return {"status": "error", "message": str(e)}

        # Upsert 所有币
        tasks = []
        for item in markets:
            coin_id = item.get("id")
            is_trending = coin_id in trending_ids
            tasks.append(CryptoAsset.upsert_from_external(item, is_trending))

        await asyncio.gather(*tasks)
        logger.info(f"✅ 虚拟货币同步完成，共 {len(markets)} 条")
        return {"status": "success", "count": len(markets)}
