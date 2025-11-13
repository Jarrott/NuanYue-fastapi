# app/api/v1/order_api.py
import json
from datetime import timedelta

from fastapi import APIRouter, Depends

from app.api.cms.services.wallet.base_wallet_sync import BaseWalletSyncService
from app.api.cms.services.wallet.wallet_secure_service import WalletSecureService
from app.api.v1.model.shop_product import ShopProduct
from app.api.v1.schema.user import CreateShopSchema
from app.extension.google_tools.rtdb_message import rtdb_msg
from app.extension.rabbitmq.constances import QUEUE_ORDER_DELAY
from app.extension.websocket.tasks.ws_user_notify import notify_user
from app.pedro import async_session_factory
from app.api.v1.model.order import Order
from app.extension.rabbitmq.rabbit import rabbit as rabbitmq_service, rabbit
from app.extension.redis.redis_client import rds
from app.pedro.pedro_jwt import login_required
from app.pedro.response import PedroResponse

rp = APIRouter(prefix="/order", tags=["订单"])


@rp.post("/create", name="用户端下单")
async def create_order(data: CreateShopSchema, user=Depends(login_required)):
    shop = await ShopProduct.get(id=data.product_id,one=True)
    data.amount = shop.price * data.quantity

    order = await Order.create(user_id=user.id, product_id=data.product_id,
                               amount=data.amount, quantity=1, commit=True)
    if order:
        # 同步钱包金额
        # ✅ 扣除钱包余额
        result = await WalletSecureService.debit_wallet(
            uid=user.id,
            amount=data.amount,
            reference=f"order:{order.id}",
            desc="订单支付扣款"
        )
        body = json.loads(result.body.decode())
        balance_after = body["data"]["balance_after"]
        # ✅ Firestore 同步钱包余额
        await BaseWalletSyncService.sync_all(user.uuid,balance_after)

    print(f"🆔 创建订单成功 ID={order.id}")
    r = await rds.instance()
    await r.setex(f"order:{order.id}:status", timedelta(seconds=10), "PENDING")

    # 10s 秒  / m 分 /h 时
    await rabbit.publish_delay(
        message={
            "task_type": "cart_expire",  # 👈 指定任务类型
            "order_id": order.id,
            "user_id": user.id,
            "product_id": data.product_id, },
        delay_ms="20s"
    )
    # 通知用户
    await notify_user(order.user_id, {
        "event": "order_created",
        "order_id": order.id,
        "price": data.amount,
        "msg": "订单创建成功 ✅"
    })

    # 通知后台，有新的订单更新
    await rtdb_msg.send_message(user.id, "您的订单已发货 ✅")

    return PedroResponse.success(msg=f"商品{order.id}下单成功")


@rp.get("/tt")
async def _expire():
    r = await rds.instance()
    await r.setex(f"order:11:status", timedelta(seconds=10), "PENDING")
    return True


@rp.get("/{order_id}")
async def get_order(order_id: int):
    """查询订单状态"""
    status = await rds.get(f"order:{order_id}:status")
    return {"order_id": order_id, "status": status or "unknown"}
