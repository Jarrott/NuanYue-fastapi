"""
# @Time    : 2025/10/28 21:40
# @Author  : Pedro
# @File    : crypto_assets.py
# @Software: PyCharm
"""
from sqlalchemy import (
    Column, Integer, String, Numeric, JSON, DateTime, Boolean, select
)
from datetime import datetime
from typing import Optional

from app.pedro.db import get_session
from app.pedro.interface import InfoCrud
from app.pedro.logger import logger


class CryptoAsset(InfoCrud):
    """虚拟货币模型（含热门标记）"""

    __tablename__ = "crypto_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    coin_id = Column(String(50), unique=True, nullable=False)
    symbol = Column(String(20))
    name = Column(String(100))
    image = Column(String(300))
    current_price = Column(Numeric(18, 6))
    market_cap = Column(Numeric(20, 2))
    market_cap_rank = Column(Integer)
    total_volume = Column(Numeric(20, 2))
    price_change_percentage_24h = Column(Numeric(10, 2))
    sparkline = Column(JSON)
    last_updated = Column(DateTime, default=datetime.utcnow)
    source = Column(String(50), default="coingecko")

    # 🔥 热门标签
    is_hot = Column(Boolean, default=False)
    # 📈 趋势标签（热门搜索）
    is_trending = Column(Boolean, default=False)

    # ======================================================
    # 异步 Upsert
    # ======================================================
    @classmethod
    async def upsert_from_external(cls, data: dict, is_trending: bool = False):
        """
        异步 Upsert 带热门标签判断
        """
        coin_id = str(data.get("id"))
        if not coin_id:
            logger.warning("⚠️ 跳过无效数据（缺少 id）")
            return None

        # 自动计算热门（基于市值、成交量、涨幅）
        market_cap_rank = data.get("market_cap_rank")
        total_volume = data.get("total_volume") or 0
        price_change = data.get("price_change_percentage_24h") or 0

        is_hot = bool(
            (market_cap_rank and market_cap_rank <= 20)
            or (total_volume > 1_000_000_000)
            or (abs(price_change) >= 5)
        )

        fields = dict(
            coin_id=coin_id,
            symbol=data.get("symbol"),
            name=data.get("name"),
            image=data.get("image"),
            current_price=data.get("current_price"),
            market_cap=data.get("market_cap"),
            market_cap_rank=market_cap_rank,
            total_volume=total_volume,
            price_change_percentage_24h=price_change,
            sparkline=data.get("sparkline_in_7d"),
            last_updated=datetime.utcnow(),
            is_hot=is_hot,
            is_trending=is_trending,
            source="coingecko",
        )

        async with get_session() as session:
            result = await session.execute(select(cls).where(cls.coin_id == coin_id))
            asset: Optional[cls] = result.scalar_one_or_none()

            if asset:
                for k, v in fields.items():
                    setattr(asset, k, v)
                await session.commit()
                await session.refresh(asset)
                logger.info(f"🔁 更新币种: {asset.name}")
                return asset
            else:
                asset = cls(**fields)
                session.add(asset)
                await session.commit()
                await session.refresh(asset)
                logger.info(f"✅ 新增币种: {asset.name}")
                return asset
