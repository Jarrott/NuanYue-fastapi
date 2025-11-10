# @Time    : 2025/11/10 06:30
# @Author  : Pedro
# @File    : mock_order_service.py
# @Software: PyCharm
"""
🎭 Pedro-Core MockOrderService (Enhanced Version)
支持 Firestore / PostgreSQL 双通道商品价格修正，
自动计算 price / total_price，防止为 0。
"""

import asyncio
import random
import uuid
from datetime import datetime
from sqlalchemy import select
from firebase_admin.firestore import firestore
from app.api.v1.model.virtual_order import Order
from app.api.v1.model.virtual_users import VirtualUser
from app.api.v1.model.shop_product import ShopProduct
from app.extension.google_tools.firestore import fs_service as fs
from app.extension.google_tools.fs_transaction import SERVER_TIMESTAMP
from app.extension.rabbitmq.rabbit import rabbit
from app.pedro.db import async_session_factory
from app.pedro.response import PedroResponse


class MockOrderService:
    # ======================================================
    # 🔹 获取虚拟用户
    # ======================================================
    @staticmethod
    async def get_virtual_users(limit: int = 5):
        async with async_session_factory() as session:
            result = await session.execute(
                select(
                    VirtualUser.id,
                    VirtualUser.username,
                    VirtualUser.email,
                    VirtualUser.address,
                    VirtualUser.region,
                ).limit(limit)
            )
            users = []
            for row in result.all():
                email = row.email or "unknown@example.com"
                masked = MockOrderService.mask_email(email)
                users.append({
                    "id": str(row.id),
                    "name": row.username or "匿名用户",
                    "email": email,
                    "email_masked": masked,
                    "region": row.region or "Tokyo",
                    "address": row.address or "Tokyo, Japan"
                })
            return users

    # ======================================================
    # 🔹 邮箱脱敏
    # ======================================================
    @staticmethod
    def mask_email(email: str) -> str:
        try:
            local, domain = email.split("@")
            masked_local = local[0] + "***" + local[-1] if len(local) > 2 else local[0] + "***"
            return f"{masked_local}@{domain}"
        except Exception:
            return "****@unknown.com"

    # ======================================================
    # 🔹 获取商户商品（自动修复 price / subtotal）
    # ======================================================
    @staticmethod
    async def get_available_products_from_firestore(merchant_id: str, limit: int = 5):
        """
        从 Firestore 商家库存读取商品；
        若 Firestore 无库存文档，则从 PostgreSQL 回退加载。
        🔧 自动修正价格逻辑：merchant_price > platform_price > SQL price
        """
        products = []
        products_ref = fs.db.collection(f"users/{merchant_id}/store/meta/products")
        docs = products_ref.limit(limit).stream()

        for doc in docs:
            d = doc.to_dict() or {}
            pid = d.get("product_id") or doc.id
            price = float(d.get("merchant_price") or d.get("platform_price") or 0.0)

            # 🔧 Firestore 内没有价格时，从 SQL 回退
            if not price:
                async with async_session_factory() as session:
                    result = await session.execute(select(ShopProduct.price).where(ShopProduct.id == int(pid)))
                    sql_price = result.scalar()
                    if sql_price:
                        price = float(sql_price)

            products.append({
                "product_id": int(pid),
                "title": d.get("title") or "Unnamed Product",
                "price": round(price, 2),
                "stock": int(d.get("stock", 0)),
                "sale_price": round(float(d.get("sale_price") or price), 2),
                "retail_price": round(float(d.get("retail_price") or price), 2),
                "source": "firestore",
            })

        # 🔄 若 Firestore 无数据，则回退 PostgreSQL
        if not products:
            print(f"[WARN] 商家 {merchant_id} Firestore 无库存，回退 PostgreSQL。")
            async with async_session_factory() as session:
                result = await session.execute(
                    select(ShopProduct.id, ShopProduct.title, ShopProduct.price, ShopProduct.stock).limit(limit)
                )
                for r in result.all():
                    m = r._mapping
                    products.append({
                        "product_id": int(m["id"]),
                        "title": m["title"] or "Unnamed Product",
                        "price": float(m["price"]),
                        "stock": int(m["stock"] or 0),
                        "sale_price": float(m["sale_price"]),
                        "retail_price": float(m["retail_price"]),
                        "source": "pgsql",
                    })

        print(f"[DEBUG] 获取到可售商品: {products}")
        return products

    # ======================================================
    # 🔹 Firestore 实时库存事务
    # ======================================================
    @staticmethod
    def _reserve_stock_tx_sync(merchant_id: str, product_id: int, qty: int):
        """
        Firestore 事务：检查库存并扣减
        """
        ref = fs.db.document(f"users/{merchant_id}/store/meta/products/{product_id}")

        @firestore.transactional
        def _tx(transaction):
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                transaction.set(ref, {
                    "product_id": int(product_id),
                    "stock": 0,
                    "updated_at": SERVER_TIMESTAMP,
                }, merge=True)
                return False, 0

            data = snap.to_dict() or {}
            current = int(data.get("stock", 0))
            if current >= qty:
                transaction.update(ref, {
                    "stock": current - qty,
                    "updated_at": SERVER_TIMESTAMP,
                })
                return True, current - qty
            else:
                return False, current

        return _tx(fs.db.transaction())

    # ======================================================
    # 🔹 Firestore 写入订单（增强版：防止 price=0）
    # ======================================================
    @staticmethod
    def _write_order_to_firestore(merchant_id: str, order_id: str, user: dict, product: dict, qty: int, status: str):
        price = round(float(product.get("price", 0)), 2)
        sale_price = round(float(product.get("sale_price", 0)), 2)
        if price == 0:
            # 🔧 fallback 从 SQL 再查一次
            try:
                import asyncio
                async def _get_price(pid: int):
                    async with async_session_factory() as session:
                        result = await session.execute(select(ShopProduct.price).where(ShopProduct.id == pid))
                        return result.scalar() or 0.0
                loop = asyncio.get_event_loop()
                price = round(loop.run_until_complete(_get_price(int(product["product_id"]))), 2)
                sale_price = round(loop.run_until_complete(_get_price(int(product["sale_price"]))), 2)
            except Exception as e:
                print(f"[WARN] 获取SQL价格失败: {e}")
                price = 9.99  # fallback 占位价

        total_price = round(price * qty, 2)
        total_sale_price = round(sale_price * qty, 2)  # 商户买入价格
        fs.db.document(f"users/{merchant_id}/store/meta/orders/{order_id}").set({
            "order_id": order_id,
            "merchant_id": merchant_id,
            "user_id": user["id"],
            "buyer_name": user["name"],
            "buyer_email_masked": user["email_masked"],
            "buyer_address": user["address"],
            "buyer_region": user["region"],
            "product_id": product["product_id"],
            "title": product.get("title") or "Unnamed Product",
            "qty": qty,
            "price": price,
            "total_price": total_price,
            "total_retail_price": total_sale_price,
            "status": status,
            "purchase_required": status == "need_purchase",
            "source": product.get("source", "firestore"),
            "created_at": SERVER_TIMESTAMP,
        })

    # ======================================================
    # 🔹 创建订单（含库存事务 + MQ 延迟任务）
    # ======================================================
    @staticmethod
    async def create_mock_order(user: dict, merchant_id: str, product: dict, session):
        product_id = product.get("product_id")
        if not product_id:
            print(f"[ERROR] 缺少 product_id: {product}")
            return None, "error"

        desired_qty = random.randint(1, 3) if int(product.get("stock", 0)) > 0 else 1
        reserved, left = await asyncio.to_thread(
            MockOrderService._reserve_stock_tx_sync, merchant_id, int(product_id), desired_qty
        )
        status = "pending" if reserved else "need_purchase"
        qty = desired_qty if reserved else 1
        price = round(float(product.get("price", 0)), 2)
        if not price:
            # SQL fallback for price=0
            async with async_session_factory() as s:
                res = await s.execute(select(ShopProduct.price).where(ShopProduct.id == int(product_id)))
                sql_price = res.scalar()
                price = round(float(sql_price or 9.99), 2)

        total_price = round(price * qty, 2)
        order_id = uuid.uuid4().hex

        # ✅ 写入 SQL
        order = Order(
            user_id=user["id"],
            product_id=int(product_id),
            quantity=qty,
            amount=total_price,
            status=status,
        )
        await session.merge(order)
        await session.commit()

        # ✅ 写入 Firestore（修正版）
        MockOrderService._write_order_to_firestore(merchant_id, order_id, user, product, qty, status)

        # ✅ MQ 延迟任务
        await rabbit.publish_delay(
            message={
                "task_type": "mock_order_auto_confirm" if reserved else "mock_order_pending",
                "order_id": order_id,
                "user_id": user["id"],
                "merchant_id": merchant_id,
                "product_id": int(product_id),
                "status": status,
            },
            delay_ms="20s",
        )

        print(f"[INFO] Created order={order_id} ({status}) for product={product_id}, qty={qty}, price={price}, total={total_price}, stock_left={left}")
        return order_id, status

    # ======================================================
    # 🔹 模拟生成订单
    # ======================================================
    @classmethod
    async def simulate_orders(cls, merchant_id: str, user_count: int = 3, per_user: int = 2):
        users = await cls.get_virtual_users(user_count)
        products = await cls.get_available_products_from_firestore(merchant_id)

        if not products:
            print(f"[WARN] 商家 {merchant_id} 无商品，使用占位商品。")
            products = [{
                "product_id": -1,
                "title": "系统占位商品（待进货）",
                "price": 9.99,
                "stock": 0,
            }]

        async with async_session_factory() as session:
            success, need_purchase = [], []
            for user in users:
                for p in random.sample(products, min(per_user, len(products))):
                    order_id, status = await cls.create_mock_order(user, merchant_id, p, session)
                    if not order_id:
                        continue
                    record = {
                        "buyer": user["email_masked"],
                        "product": p["title"],
                        "order": order_id,
                        "status": status,
                    }
                    (success if status == "pending" else need_purchase).append(record)

        summary = {"success": len(success), "need_purchase": len(need_purchase)}
        return PedroResponse.success(
            data={"summary": summary, "details": success + need_purchase},
            msg=f"✅ 模拟完成：{summary['success']} 正常下单，{summary['need_purchase']} 待进货"
        )
