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
from app.extension.google_tools.fs_transaction import SERVER_TIMESTAMP, fs_service
from app.extension.rabbitmq.rabbit import rabbit
from app.pedro.db import async_session_factory
from app.pedro.response import PedroResponse


class MockOrderService:
    # ======================================================
    # 🔹 获取虚拟用户
    # ======================================================
    @staticmethod
    async def get_virtual_users(limit: int = 5):
        """
        从 Firestore 读取虚拟用户 virtual_users/{uid}
        """
        users_ref = fs_service.db.collection("virtual_users") \
            .order_by("create_time", direction=firestore.Query.DESCENDING) \
            .limit(limit)

        docs = users_ref.stream()

        users = []
        for doc in docs:
            data = doc.to_dict()
            if not data:
                continue

            email = data.get("email", "unknown@example.com")
            # masked = MockOrderService.mask_email(email)

            users.append({
                "id": doc.id,
                "name": data.get("nickname", "匿名用户"),
                "email": email,
                "email_masked": email,
                "region": data.get("city", "Tokyo"),
                "address": data.get("address", "Tokyo, Japan"),
                "phone": data.get("phone", "0"),
                "gender": data.get("gender", "Male"),
                "device": data.get("device", "0"),
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
                    select(ShopProduct.id,
                           ShopProduct.title,
                           ShopProduct.price,
                           ShopProduct.stock,
                           ShopProduct.sale_price,
                           ShopProduct.retail_price,
                           ).limit(limit)
                )
                for r in result.all():
                    m = r._mapping
                    products.append({
                        "product_id": int(m["id"]),
                        "title": m["title"] or "Unnamed Product",
                        "price": float(m["price"]),
                        "stock": int(m["stock"] or 0),
                        "sale_price": float(m.get("sale_price") or 0.0),
                        "retail_price": float(m["retail_price"] or 0.0),
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
    async def _fetch_product_detail_from_pgsql(pid: int):
        """确保从 PGSQL 获取完整商品信息"""
        async with async_session_factory() as session:
            result = await session.execute(
                select(
                    ShopProduct.id,
                    ShopProduct.title,
                    ShopProduct.price,
                    ShopProduct.sale_price,
                    ShopProduct.retail_price,
                    ShopProduct.stock,
                    ShopProduct.images,
                    ShopProduct.thumbnail,
                ).where(ShopProduct.id == pid)
            )
            row = result.mappings().first()
            if not row:
                return None

            return {
                "id": row["id"],
                "title": row["title"],
                "price": float(row["price"] or 0),
                "sale_price": float(row["sale_price"] or row["price"] or 0),
                "retail_price": float(row["retail_price"] or row["price"] or 0),
                "stock": row["stock"],
                "images": row["images"] or [],     # 你的表里 image 字段是数组
                "thumbnail": row["thumbnail"],    # 缩略图字段
            }


    @staticmethod
    async def _write_order_to_firestore(merchant_id: str, order_id: str, user: dict, product: dict, qty: int, status: str):
        """
        修复后的版本：无条件从 PGSQL 获取商品完整信息保存 items
        """

        pid = int(product["product_id"])

        # 🔥 强制从 PGSQL 获取完整商品详情（异步转同步）
        loop = asyncio.get_event_loop()
        detail = await MockOrderService._fetch_product_detail_from_pgsql(pid)

        if not detail:
            print(f"[WARN] 产品 {pid} 在 PGSQL 未找到，写入占位数据")
            detail = {
                "id": pid,
                "title": "Unknown Product",
                "price": 9.99,
                "sale_price": 9.99,
                "retail_price": 9.99,
                "images": [],
                "thumbnail": None,
            }

        price = detail["price"]
        sale_price = detail["sale_price"]
        retail_price = detail["retail_price"]

        total_price = round(price * qty, 2)

        fs.db.document(f"users/{merchant_id}/store/meta/orders/{order_id}").set({
            "order_id": order_id,
            "merchant_id": merchant_id,
            "user_id": user["id"],
            "buyer_name": user["name"],
            "buyer_email_masked": user["email_masked"],
            "buyer_address": user["address"],
            "buyer_region": user["city"],
            "product_id": pid,
            "title": detail["title"],
            "qty": qty,
            "price": price,
            "total_price": total_price,
            "total_retail_price": retail_price * qty,
            "status": status,
            "purchase_required": status == "need_purchase",
            "source": "pgsql",

            # ⭐⭐⭐ ITEMS — 最关键的修复点 ⭐⭐⭐
            "items": [
                {
                    "product_id": pid,
                    "title": detail["title"],
                    "qty": qty,
                    "price": price,
                    "total_price": total_price,
                    "sale_price": sale_price,
                    "retail_price": retail_price,

                    # 图片字段（确保永远不为空）
                    "images": detail["images"],
                    "thumbnail": detail["thumbnail"],
                    "image": detail["thumbnail"],  # 给前端兼容（旧字段）
                }
            ],

            "created_at": SERVER_TIMESTAMP,
        })

    # ======================================================
    # 🔹 创建订单（含库存事务 + MQ 延迟任务）
    # ======================================================
    @staticmethod
    async def create_mock_order(user: dict, merchant_id: str, product: dict, session):
        # 🔥如果没有传 user，自动随机从 Firestore 获取虚拟用户
        if user is None:
            user = await MockOrderService.get_random_virtual_user_from_firestore()

        product_id = product.get("product_id")
        if not product_id:
            print(f"[ERROR] 缺少 product_id: {product}")
            return None, "error"

        # 预定库存
        desired_qty = random.randint(1, 3) if int(product.get("stock", 0)) > 0 else 1
        reserved, left = await asyncio.to_thread(
            MockOrderService._reserve_stock_tx_sync, merchant_id, int(product_id), desired_qty
        )

        status = "pending" if reserved else "need_purchase"
        qty = desired_qty if reserved else 1

        # 保证价格有效
        price = round(float(product.get("price", 0)), 2)
        if not price:
            async with async_session_factory() as s:
                res = await s.execute(select(ShopProduct.price).where(ShopProduct.id == int(product_id)))
                sql_price = res.scalar()
                price = round(float(sql_price or 9.99), 2)

        total_price = round(price * qty, 2)
        today = datetime.now().strftime("%Y%m%d")
        order_id = f"ORDER-{today}-{uuid.uuid4().hex[:6]}"

        # SQL 记录
        order = Order(
            user_id=user["id"],
            product_id=int(product_id),
            quantity=qty,
            amount=total_price,
            status=status,
        )
        await session.merge(order)
        await session.commit()

        # Firestore 订单
        await MockOrderService._write_order_to_firestore(merchant_id, order_id, user, product, qty, status)

        # MQ 延迟
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

        print(
            f"[INFO] Created order={order_id} ({status}) for product={product_id}, qty={qty}, price={price}, total={total_price}, stock_left={left}"
        )
        return order_id, status

    # ======================================================
    # 🔹 模拟生成订单
    # ======================================================
    @classmethod
    async def simulate_orders(cls, merchant_id: str, order_count: int = 10):
        """
        🔥 每条订单自动随机选择一个 Firestore 虚拟用户
        """
        products = await cls.get_available_products_from_firestore(merchant_id)

        if not products:
            print(f"[WARN] 商家 {merchant_id} 无商品，使用占位商品.")
            products = [{
                "product_id": -1,
                "title": "系统占位商品（待进货）",
                "price": 9.99,
                "stock": 0,
            }]

        async with async_session_factory() as session:
            success, need_purchase = [], []

            # 🆕 每条订单随机一个用户
            for _ in range(order_count):
                user = None  # 交给 create_mock_order 处理
                p = random.choice(products)

                order_id, status = await cls.create_mock_order(user=user,merchant_id=merchant_id, product=p, session=session)
                if not order_id:
                    continue

                record = {
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

    @staticmethod
    async def get_random_virtual_user_from_firestore():
        """
        随机从 Firestore 的 virtual_users 集合中选择一个虚拟用户。
        """
        try:
            # 读取所有虚拟用户文档（数量一般几十到几百，可接受）
            docs = await fs_service.list_documents("virtual_users")

            if not docs:
                return {
                    "id": "u_000000",
                    "name": "Guest User",
                    "email": "guest@example.com",
                    "email_masked": "guest@example.com",
                    "address": "Unknown",
                    "city": "Unknown",
                    "country": "Unknown"
                }

            # 随机选一个
            d = random.choice(docs)
            data = d.to_dict() or {}

            return {
                "id": d.id,
                "name": data.get("nickname") or data.get("name") or "Unknown User",
                "email": data.get("email", "unknown@example.com"),
                "email_masked": data.get("email", "unknown@example.com"),
                "phone": data.get("phone"),
                "address": data.get("address"),
                "city": data.get("city"),
                "country": data.get("country"),
                "gender": data.get("gender"),
                "device": data.get("device"),
                "categories": data.get("preferred_categories", []),
            }

        except Exception as e:
            print(f"[ERROR] 获取虚拟用户失败: {e}")
            return None