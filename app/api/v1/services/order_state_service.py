import datetime
import json
from typing import Optional, Dict, Any, List

from sqlalchemy import select, update, and_, func
from starlette.responses import Response

from app.api.cms.services.wallet.base_wallet_sync import BaseWalletSyncService
from app.api.cms.services.wallet.wallet_secure_service import WalletSecureService
from app.pedro.db import async_session_factory
from app.api.v1.model.shop_orders import ShopOrders as Order, ShopOrders, ShopOrderItem


class OrderStateService:
    @staticmethod
    async def list_orders(
            *,
            uid: Optional[str] = None,
            page: int = 1,
            page_size: int = 10,
            status: Optional[str] = None,
            keyword: Optional[str] = None,
            start_date: Optional[str] = None,
            end_date: Optional[str] = None,
            self_only: bool = True
    ) -> Dict[str, Any]:

        filters = []

        # 用户端只能查看自己的订单
        if self_only and uid:
            filters.append(ShopOrders.user_id == uid)

        # 后台可查所有订单时，不传 self_only=true
        if status:
            filters.append(ShopOrders.status == status)

        if keyword:
            filters.append(ShopOrders.order_no.ilike(f"%{keyword}%"))

        if start_date:
            filters.append(ShopOrders.create_time >= datetime.datetime.fromisoformat(start_date))

        if end_date:
            filters.append(ShopOrders.create_time <= datetime.datetime.fromisoformat(end_date))

        async with async_session_factory() as session:

            base_query = select(ShopOrders).where(and_(*filters)).order_by(ShopOrders.create_time.desc())

            # 分页
            count_query = select(func.count()).select_from(ShopOrders).where(and_(*filters))
            total = (await session.execute(count_query)).scalar_one()

            result = await session.execute(
                base_query.offset((page - 1) * page_size).limit(page_size)
            )

            orders: List[ShopOrders] = result.scalars().all()

            data = [
                {
                    "order_id": o.id,
                    "order_no": o.order_no,
                    "status": o.status,
                    "total": float(o.total),
                    "create_time": o.create_time.isoformat(),
                    "paid_at": o.update_time.isoformat() if o.update_time else None,
                    "tracking_number": o.tracking_number,
                }
                for o in orders
            ]

            return {
                "page": page,
                "page_size": page_size,
                "total": total,
                "data": data
            }

    @staticmethod
    async def get_order_detail(uid: str, order_id: int):
        async with async_session_factory() as session:
            # 先查询订单主表
            result = await session.execute(
                select(ShopOrders).where(
                    ShopOrders.id == order_id,
                    ShopOrders.user_id == uid
                )
            )
            order = result.scalar_one_or_none()

            if not order:
                raise ValueError("Order not found")

            # 查询订单商品
            items_result = await session.execute(
                select(ShopOrderItem).where(ShopOrderItem.order_id == order_id)
            )
            items = items_result.scalars().all()

            # 格式化数据返回给前端
            return {
                "order_id": order.id,
                "status": order.status,
                "address_id": order.address_id,
                "subtotal": float(order.subtotal),
                "shipping_fee": float(order.shipping_fee),
                "discount": float(order.discount),
                "total": float(order.total),
                "created_at": str(order.create_time) if hasattr(order, "create_time") else None,
                "items": [
                    {
                        "product_id": i.product_id,
                        "quantity": i.quantity,
                        "unit_price": float(i.unit_price),
                        "subtotal": float(i.subtotal),
                    }
                    for i in items
                ]
            }

    @staticmethod
    async def _get_order(order_id, uid=None):
        async with async_session_factory() as session:
            stmt = select(Order).where(Order.order_no == order_id)
            if uid:
                stmt = stmt.where(Order.user_id == uid)

            result = await session.execute(stmt)
            order = result.scalar_one_or_none()

            if not order:
                raise ValueError("Order not found")
            return order

    @staticmethod
    async def pay(order_id: str, uid: str, method: str = "WALLET"):

        # 1️⃣ 获取订单
        order = await OrderStateService._get_order(order_id, uid)

        if order.status != "PENDING":
            raise ValueError(f"Order cannot be paid (current state: {order.status})")

        amount = float(order.total)

        # 2️⃣ 执行扣款
        debit_result = await WalletSecureService.debit_wallet(
            uid=uid,
            amount=amount,
            reference=f"ORDER-{order.id}",
            channel="order",
            desc="订单支付",
            operator_id=uid,
        )

        # 3️⃣ 兼容 Response / dict
        if isinstance(debit_result, Response):
            payload = json.loads(debit_result.body.decode())
        else:
            payload = debit_result

        # print("\n🚩 Wallet Response → ", payload)

        # 4️⃣ 幂等处理（⚠ 不用取 data）
        msg = payload.get("msg", "")
        if "重复" in msg or "幂等" in msg:
            return {
                "order_id": order.id,
                "status": "ALREADY_PAID",
                "message": msg
            }

        # 5️⃣ 解析正常 data
        data = payload.get("data") or {}
        status = data.get("status")

        if status != "ok":
            raise ValueError(f"Wallet payment failed: {msg}")

        balance_after = data.get("balance_after")

        # 6️⃣ 多源同步
        await BaseWalletSyncService.sync_all(uid, balance_after)

        # 7️⃣ 更新订单状态
        async with async_session_factory() as session:
            order.status = "PAID"
            order.payment_method = method
            order.paid_at = datetime.datetime.utcnow()
            session.add(order)
            await session.commit()

        return {
            "order_id": order.id,
            "status": "PAID",
            "payment_method": method,
            "balance_after": balance_after
        }

    @staticmethod
    async def cancel(order_id: str, uid: str):
        order = await OrderStateService._get_order(order_id, uid)

        if order.status not in ["PENDING", "PAID"]:
            raise ValueError("This order cannot be cancelled now")

        order.status = "CANCELLED"

        async with async_session_factory() as session:
            session.add(order)
            await session.commit()

        return {"order_id": order.order_no, "status": order.status}

    @staticmethod
    async def ship(order_id: str, tracking_number: str):
        order = await OrderStateService._get_order(order_id)

        if order.status not in ["PAID", "PROCESSING"]:
            raise ValueError("Cannot ship this order")

        order.status = "SHIPPED"
        order.tracking_number = tracking_number

        async with async_session_factory() as session:
            session.add(order)
            await session.commit()

        return {"order_id": order.order_no, "status": order.status}

    @staticmethod
    async def complete(order_id: str):
        order = await OrderStateService._get_order(order_id)

        if order.status != "SHIPPED":
            raise ValueError("Order must be shipped before completion")

        order.status = "DONE"

        async with async_session_factory() as session:
            session.add(order)
            await session.commit()

        return {"order_id": order.order_no, "status": order.status}
