from app.api.v1.model.order import Order
from app.extension.redis.redis_client import rds
from app.extension.eventbus import eventbus

#要在__init__引入
async def handle_order_timeout(data: dict):
    order_id = data.get("order_id")
    if not order_id:
        return print("⚠️ order_timeout: 缺少 order_id")

    # 避免重复处理
    cache = await rds.get(f"order:{order_id}:status")
    if cache in ("PAID", "CANCELED", "EXPIRED"):
        return print(f"⏭️ 已跳过订单 {order_id}, 状态={cache}")

    # 更新数据库
    order = await Order.get(id=order_id)
    if not order:
        return print(f"❌ 找不到订单 {order_id}")

    await order.update(status="CANCELED", commit=True)
    await rds.set(f"order:{order_id}:status", "CANCELED", ex=3600)

    # 发通知
    await eventbus.publish("order.timeout", {"order_id": order_id, "user_id": order.user_id})
    print(f"✅ 订单 {order_id} 已自动取消 (未支付超时)")
