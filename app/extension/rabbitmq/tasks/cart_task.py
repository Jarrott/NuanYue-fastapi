from app.api.v1.model.order import Order
from app.api.v1.model.shop_product import ShopProduct
from app.extension.redis.redis_client import rds
from app.extension.eventbus import eventbus


# =====================================================
# 商品下单未支付 → 自动取消订单 + 释放库存 + 推送前端
# =====================================================
async def handle_cart_expire(data: dict):
    order_id = data.get("order_id")
    user_id = data.get("user_id")
    product_id = data.get("product_id")

    if not (order_id and user_id and product_id):
        print("⚠️ [cart_expire] 无效消息: 缺少 order_id / user_id / product_id")
        return

    r = await rds.instance()

    # ✅ 防重复执行（幂等）
    cache_key = f"order:{order_id}:status"
    cache_status = await r.get(cache_key)
    if cache_status in ["PAID", "EXPIRED", "CANCELED"]:
        print(f"⏭️ [cart_expire] 跳过订单 {order_id} 状态={cache_status}")
        return

    # ✅ 获取订单
    order = await Order.get(id=order_id)
    if not order:
        print(f"❌ [cart_expire] 未找到订单: {order_id}")
        return

    if order.status in ["PAID", "EXPIRED", "CANCELED"]:
        print(f"⏭️ [cart_expire] 跳过订单 {order_id} 状态={order.status}")
        return

    # ✅ 标记为已超时
    await order.update(status="EXPIRED", commit=True)

    # ✅ 恢复库存
    product = await ShopProduct.get(id=product_id)
    if product:
        await product.update(
            quantity_available=product.quantity_available + order.quantity,
            commit=True
        )
        print(f"📦 [cart_expire] +库存 product={product_id} +{order.quantity}")

    # ✅ Redis 标记状态
    await r.setex(cache_key, 86000, "EXPIRED")

    # ✅ 通知前端
    await eventbus.publish("order.expired", {
        "order_id": order_id,
        "user_id": user_id,
        "product_id": product_id,
        "status": "EXPIRED",
        "msg": "订单超时未支付，已自动取消"
    })

    print(f"⌛ [cart_expire] 订单 {order_id} 超时取消 + 恢复库存 ✅")
