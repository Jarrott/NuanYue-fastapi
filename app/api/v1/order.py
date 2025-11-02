# app/api/v1/order_api.py
from datetime import timedelta

from fastapi import APIRouter

from app.extension.google_tools.rtdb_message import rtdb_msg
from app.extension.rabbitmq.constances import QUEUE_ORDER_DELAY
from app.extension.websocket.tasks.ws_user_notify import notify_user
from app.pedro import async_session_factory
from app.api.v1.model.order import Order
from app.extension.rabbitmq.rabbit import rabbit as rabbitmq_service, rabbit
from app.extension.redis.redis_client import rds

rp = APIRouter(prefix="/order", tags=["订单"])


@rp.post("/create")
async def create_order():
    user_id, product_id, amount = 1, 1001, 100

    order = await Order.create(user_id=user_id, product_id=product_id,
                               amount=amount, quantity=1, commit=True)
    print(f"🆔 创建订单成功 ID={order.id}")
    r = await rds.instance()
    await r.setex(f"order:{order.id}:status", timedelta(seconds=10), "PENDING")

    # 10s 秒  / m 分 /h 时
    await rabbit.publish_delay(
        message={
            "task_type": "cart_expire",  # 👈 指定任务类型
            "order_id": order.id,
            "user_id": user_id,
            "product_id": product_id},
        delay_ms="20s"
    )
    # 通知用户
    await notify_user(order.user_id, {
        "event": "order_created",
        "order_id": order.id,
        "price": amount,
        "msg": "订单创建成功 ✅"
    })

    # 通知后台，有新的订单更新
    await rtdb_msg.send_message(user_id, "您的订单已发货 ✅")

    return {"msg": "订单创建成功，10秒后完成", "order_id": order.id}

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

