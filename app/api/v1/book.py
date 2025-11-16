from fastapi import APIRouter, Depends

from app.api.cms.schema.admin import AdminBroadcastSchema, PushMessageSchema
from app.api.v1.model.crypto_assets import CryptoAsset
from app.config.settings_manager import get_current_settings
from app.extension.rabbitmq.rabbit import rabbit
from app.extension.websocket.tasks.ws_user_notify import notify_broadcast, notify_user
from app.pedro import async_session_factory
from app.pedro.exception import Success, NotFound
from app.extension.redis.redis_client import rds
from app.pedro.response import PedroResponse
from app.util.get_lang import get_lang

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


@rp.post("/push/all/message")
async def broadcast_system_announcement(data: AdminBroadcastSchema, lang: str = Depends(get_lang)):
    # 全局广播参数
    await notify_broadcast(
        {**data.model_dump(), "lang": lang},
    )
    return PedroResponse.success(msg="信息已成功推送")


@rp.post("/push/message/{uid}")
async def broadcast_user_message(uid: int, data: PushMessageSchema):
    await notify_user(uid=uid, event={**data.model_dump()}, lang=data.lang)

    return PedroResponse.success(msg="信息已成功推送")
