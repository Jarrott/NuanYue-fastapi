# app/extension/rabbitmq/consumer_order.py
from app.extension.redis.redis_client import rds
from app.extension.eventbus import eventbus
from app.api.v1.model.order import Order
from app.pedro import async_session_factory

async def handle_order_expire(data: dict):
    order_id = (data or {}).get("order_id")
    if not order_id:
        print("⚠️ 无效消息: 无 order_id")
        return


    order = await Order.get(id=order_id)
    if not order:
        print(f"❌ 未找到订单: {order_id}")
        return

    await order.update(status="completed", commit=True)
    await rds.set(f"order:{order_id}:status", "completed", ex=600)

    await eventbus.publish("order.completed", {"order_id": order_id, "user_id":order.user_id,"status": "completed"})
    print(f"✅ 订单 {order_id} 完成（已通过 EventBus 推送）")
