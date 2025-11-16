from app.api.v1.model.shop_orders import ShopOrderItem
from app.api.v1.model.shop_orders import ShopOrders
from app.api.v1.model.user_address import UserAddress

from app.api.v1.services.cart_service import CartService
from app.extension.rabbitmq.rabbit import rabbit
from app.pedro import async_session_factory
from app.pedro.response import PedroResponse
from app.util.order_number_generator import OrderNumberGenerator


class CheckoutService:

    @staticmethod
    async def checkout(uid: str, address_id: int):
        address_id = UserAddress.get(id=address_id)
        if not address_id:
            return PedroResponse.fail(msg="Address not found")

        cart = await CartService.get_cart(uid)
        if not cart["items"]:
            raise ValueError("Cart is empty")

        # 示例：固定运费逻辑
        shipping_fee = 4.00
        discount = 0.00

        subtotal = cart["total"]
        total = subtotal + shipping_fee - discount

        async with async_session_factory() as session:
            # 保存订单
            order = ShopOrders(
                user_id=uid,
                order_no=str(OrderNumberGenerator.generate(uid)),
                subtotal=subtotal,
                total=total,
                shipping_fee=shipping_fee,
                discount=discount,
                address_id=address_id
            )
            session.add(order)
            await session.flush()  # 获取 order.id

            # 保存订单详情
            for item in cart["items"]:
                entry = ShopOrderItem(
                    order_id=order.id,
                    product_id=item["product_id"],
                    quantity=item["quantity"],
                    unit_price=item["price"],
                    subtotal=item["subtotal"]
                )
                session.add(entry)

            await session.commit()

        # 🔄 推送到 MQ 做库存扣减 / 后台处理
        await rabbit.publish_delay(message={"task_type": "order.create", "order_id": order.id, "user_id": uid},
                                   delay_ms="1d")

        # 清空购物车
        await CartService.clear(uid)

        return {"order_no": order.order_no, "total": total}
