# app/api/v1/order_api.py
from fastapi import APIRouter

from app.extension.rabbitmq.constances import QUEUE_ORDER_DELAY
from app.pedro import async_session_factory
from app.api.v1.model.order import Order
from app.extension.rabbitmq.rabbit import rabbit as rabbitmq_service, rabbit
from app.extension.redis.redis_client import rds

rp = APIRouter(prefix="/order", tags=["订单测试"])


@rp.post("/create")
async def create_order():
    user_id, product_id, amount = 1, 1001, 100

    order = await Order.create(user_id=user_id, product_id=product_id,
                               amount=amount, commit=True)
    print(f"🆔 创建订单成功 ID={order.id}")

    await rabbit.publish_delay(
        message={"order_id": order.id, "user_id": user_id},
        delay_ms=10000
    )

    return {"msg": "订单创建成功，10秒后完成", "order_id": order.id}

# 临时增加一个调试接口
@rp.get("/_debug/rabbit")
async def debug_rabbit():
    ch = await rabbit._ensure_channel()
    # passive=True 不会创建，仅获取属性；不存在则报错，便于定位
    q = await ch.declare_queue(QUEUE_ORDER_DELAY, passive=True)
    return {"queue": QUEUE_ORDER_DELAY, "message_count": q.declaration_result.message_count}


@rp.get("/{order_id}")
async def get_order(order_id: int):
    """查询订单状态"""
    status = await rds.get(f"order:{order_id}:status")
    return {"order_id": order_id, "status": status or "unknown"}
