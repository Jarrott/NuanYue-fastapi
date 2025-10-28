from fastapi import APIRouter

from app.api.v1.model.crypto_assets import CryptoAsset
from app.config.settings_manager import get_current_settings
from app.extension.rabbitmq.rabbit import rabbit
from app.pedro import async_session_factory
from app.pedro.exception import Success, NotFound
from app.extension.redis.redis_client import rds

rp = APIRouter(prefix="/book", tags=["图书"])


@rp.get("/api")
async def login():
    settings = get_current_settings()
    print(settings.extra.default)
    await rds.set("user:1001", {"name": "Pedro", "vip": True}, ex=3600)
    await rabbit.publish("ok", routing_key="task_queue")
    return Success("✅ book api loaded successfully")


async def example_usage():
    """FastAPI ORM 异步 CRUD 样例"""

    # ✅ 查询热门币
    trending = await CryptoAsset.get(one=False, is_trending=True)

    # ✅ 获取计数
    total = await CryptoAsset.count(source="coingecko")

    # ✅ 更新单条
    asset = trending[0]
    await asset.update(current_price=1234.56, commit=True)

    # ✅ 新增币种
    await CryptoAsset.create(coin_id="eth", symbol="ETH", name="Ethereum")

    # ✅ Upsert（存在则更新）
    await CryptoAsset.upsert(
        where={"coin_id": "btc"},
        data={"name": "Bitcoin", "market_cap": 1234567890},
    )
