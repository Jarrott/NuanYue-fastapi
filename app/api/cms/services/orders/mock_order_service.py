# @Time    : 2025/11/9 23:30
# @Author  : Pedro
# @File    : mock_order_service.py
# @Software: PyCharm
"""
🎭 Pedro-Core MockOrderService (with MQ Delay Tasks)
生成虚拟订单并推送延迟任务（支持 cart_expire、mock_order_auto_confirm 等类型）。
"""

import asyncio
import random
import uuid
from datetime import datetime
from sqlalchemy import select
from firebase_admin.firestore import firestore
from app.api.v1.model.virtual_order import Order
from app.api.v1.model.virtual_users import VirtualUser
from app.extension.google_tools.firestore import fs_service as fs
from app.extension.google_tools.fs_transaction import SERVER_TIMESTAMP
from app.extension.rabbitmq.rabbit import rabbit
from app.pedro.db import async_session_factory
from app.pedro.response import PedroResponse


class MockOrderService:
    # ======================================================
    # 🔹 从 PostgreSQL 获取虚拟用户（带隐私字段）
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
    # 🔹 获取商户库存商品（Firestore + PostgreSQL回退）
    # ======================================================
    @staticmethod
    async def get_available_products_from_firestore(merchant_id: str, limit: int = 5):
        """
        从 Firestore 商家库存读取可售商品；
        若 Firestore 无库存文档，则从 PostgreSQL 回退加载（stock=0 表示未进货）。
        """
        products = []
        products_ref = fs.db.collection(f"users/{merchant_id}/store/meta/products")
        docs = products_ref.limit(limit).stream()

        for doc in docs:
            d = doc.to_dict() or {}
            pid = d.get("product_id") or doc.id
            products.append({
                "product_id": int(pid),
                "title": d.get("title") or "Unnamed Product",
                "price": float(d.get("merchant_price", d.get("platform_price", 0.0))),
                "stock": int(d.get("stock", 0)),
                "source": "firestore",
            })

        if not products:
            print(f"[WARN] 商家 {merchant_id} 无库存文档，回退 PostgreSQL。")
            from app.api.v1.model.shop_product import ShopProduct
            async with async_session_factory() as session:
                result = await session.execute(
                    select(ShopProduct.id, ShopProduct.title, ShopProduct.price, ShopProduct.stock).limit(limit)
                )
                rows = result.all()
                for row in rows:
                    m = row._mapping
                    products.append({
                        "product_id": int(m["id"]),
                        "title": m["title"] or "Unnamed Product",
                        "price": float(m["price"]),
                        "stock": 0,
                        "source": "pgsql",
                    })

        print(f"[DEBUG] 获取到可售商品: {products}")
        return products

    # ======================================================
    # 🔹 Firestore 实时库存读取 / 扣减事务
    # ======================================================
    @staticmethod
    def _reserve_stock_tx_sync(merchant_id: str, product_id: int, qty: int):
        """
        Firestore 事务：若库存足够 → 扣减库存并返回 True；
        否则 → 返回 False, 不修改库存。
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
    # 🔹 写入 Firestore 订单
    # ======================================================
    @staticmethod
    def _write_order_to_firestore(merchant_id: str, order_id: str, user: dict, product: dict, qty: int, total_price: float, status: str):
        fs.db.document(f"users/{merchant_id}/store/meta/orders/{order_id}").set({
            "order_id": order_id,
            "merchant_id": merchant_id,
            "user_id": user["id"],
            "buyer_name": user["name"],
            "buyer_email_masked": user["email_masked"],
            "buyer_address": user["address"],
            "buyer_region": user["region"],
            "product_id": product["product_id"],
            "title": product["title"],
            "qty": qty,
            "price": product["price"],
            "total_price": total_price,
            "status": status,
            "purchase_required": status == "need_purchase",
            "source": product.get("source", "firestore"),
            "created_at": SERVER_TIMESTAMP,
        })

    # ======================================================
    # 🔹 创建订单（含库存事务与MQ延迟任务）
    # ======================================================
    @staticmethod
    async def create_mock_order(user: dict, merchant_id: str, product: dict, session):
        product_id = product.get("product_id")
        if not product_id:
            print(f"[ERROR] 商品缺少 product_id: {product}")
            return None, "error"

        # 若有库存，随机下 1~3 件，否则仅下 1 件
        desired_qty = random.randint(1, 3) if int(product.get("stock", 0)) > 0 else 1

        # 🔐 Firestore事务占库存
        reserved, left = await asyncio.to_thread(
            MockOrderService._reserve_stock_tx_sync, merchant_id, int(product_id), desired_qty
        )

        status = "pending" if reserved else "need_purchase"
        qty = desired_qty if reserved else 1
        total_price = round(float(product["price"]) * qty, 2)
        order_id = uuid.uuid4().hex

        # ✅ 写入 PostgreSQL
        order = Order(
            user_id=user["id"],
            product_id=int(product_id),
            quantity=qty,
            amount=total_price,
            status=status,
        )
        await session.merge(order)
        await session.commit()

        # ✅ 写入 Firestore
        MockOrderService._write_order_to_firestore(merchant_id, order_id, user, product, qty, total_price, status)

        # ✅ MQ 延迟任务
        task_type = "mock_order_auto_confirm" if reserved else "mock_order_pending"
        await rabbit.publish_delay(
            message={
                "task_type": task_type,
                "order_id": order_id,
                "user_id": user["id"],
                "merchant_id": merchant_id,
                "product_id": int(product_id),
                "status": status,
            },
            delay_ms="20s",
        )

        print(f"[INFO] Created order={order_id} ({status}) for product={product_id}, qty={qty}, stock_left={left}")
        return order_id, status

    # ======================================================
    # 🔹 主流程：批量生成模拟订单
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
