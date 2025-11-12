# @Time    : 2025/11/10 04:10
# @Author  : Pedro
# @File    : merchant_service.py
# @Software: PyCharm
"""
🔥 Pedro-Core MerchantService (优化版)
商户核心服务模块：钱包 + 店铺采购
结构优化：
  ✅ 支持 Firestore 批次结构（含多商品 items）
  ✅ 统一分页返回格式（PedroResponse.page）
  ✅ 优化 SQL 联查与数据补全
"""

import asyncio
import uuid
from typing import List, Dict, Any
from firebase_admin.firestore import firestore
from sqlalchemy import select, update
from sqlalchemy.orm import load_only

from app.extension.google_tools.firebase_admin_service import fs
from app.extension.google_tools.fs_transaction import SERVER_TIMESTAMP, fs_service

from app.api.v1.model.shop_product import ShopProduct
from app.pedro.db import async_session_factory
from app.api.cms.services.wallet.wallet_secure_service import WalletSecureService
from app.pedro.response import PedroResponse


class MerchantService:
    @staticmethod
    async def create_merchant(
            uid: str,
            name: str = None,
            email: str = None,
            address: str = None,
            logo: str = None,
            lang: str = None
    ):
        """
        🏪 创建商家档案 (Firestore)
        路径: users/{uid}/store/profile
        """

        store_ref = fs.document(f"users/{uid}/store/profile")

        data = {
            "store_id": uuid.uuid4().hex,
            "store_name": name or "Unnamed Store",
            "email": email,
            "lang": lang or "en",
            "address": address,
            "logo": logo,
            "status": "pending",
            "verify_badge": False,
            "level": "bronze",
            "create_time": SERVER_TIMESTAMP,
            "update_time": SERVER_TIMESTAMP,
        }

        store_ref.set(data, merge=True)
        print(f"✅ Firestore: Created merchant profile for user {uid}")

        return PedroResponse.success(msg="申请开通店铺成功")

    # ==============================================================
    # 📦 批量采购（Firestore 事务 + SQL 同步）
    # ==============================================================
    @staticmethod
    async def purchase_batch(uid: str, items: list[dict[str, int]]) -> PedroResponse:
        """
        商户批量采购接口
        Firestore 批次文档写入统一字段：
          - batch_id
          - items: [{product_id, product_name, quantity, unit_price, subtotal}]
          - total_amount
          - status: purchased
          - created_at (用该字段排序)
        """
        # 1) 读取 SQL 商品信息
        async with async_session_factory() as session:
            ids = [int(i["product_id"]) for i in items]
            result = await session.execute(select(ShopProduct).where(ShopProduct.id.in_(ids)))
            products = {int(p.id): p for p in result.scalars().all()}

        # 2) 计算总价（确保非 0）
        batch_items = []
        total_cost = 0.0
        for it in items:
            pid = int(it["product_id"])
            qty = int(it["quantity"])
            p = products.get(pid)
            if not p:
                return PedroResponse.fail(msg=f"商品不存在: {pid}")
            unit_price = float(p.price)
            subtotal = round(unit_price * qty, 2)
            total_cost += subtotal
            batch_items.append({
                "product_id": pid,
                "product_name": p.title,
                "quantity": qty,
                "unit_price": unit_price,
                "subtotal": subtotal,
            })

        total_cost = round(total_cost, 2)
        if total_cost <= 0:
            return PedroResponse.fail(msg="总价计算异常（0）")

        # 3) Firestore 事务：扣余额 + 写批次 + 增库存（商家侧）
        batch_id = uuid.uuid4().hex
        purchase_ref = fs.db.document(f"users/{uid}/store/meta/purchases/{batch_id}")

        @firestore.transactional
        def _tx(transaction):
            wallet_ref = fs.db.document(f"users/{uid}/store/wallet")
            snap = wallet_ref.get(transaction=transaction)
            balance = float((snap.to_dict() or {}).get("available_balance", 0.0))
            if balance < total_cost:
                raise ValueError(f"余额不足：{balance:.2f} < {total_cost:.2f}")

            # 扣余额
            transaction.update(wallet_ref, {
                "available_balance": firestore.Increment(-total_cost),
                "updated_at": firestore.SERVER_TIMESTAMP,
            })

            # 写批次
            transaction.set(purchase_ref, {
                "batch_id": batch_id,
                "items": batch_items,  # ✅ 单价/小计完整
                "total_amount": total_cost,  # ✅ 非 0
                "status": "purchased",
                "created_at": firestore.SERVER_TIMESTAMP,  # ✅ 统一使用 created_at
            })

            # 商家库存累加
            for it in batch_items:
                pid, qty = it["product_id"], int(it["quantity"])
                product_ref = fs.db.document(f"users/{uid}/store/meta/products/{pid}")
                transaction.set(product_ref, {
                    "product_id": pid,
                    "title": it["product_name"],
                    "stock": firestore.Increment(qty),
                    "merchant_price": it["unit_price"],
                    "updated_at": firestore.SERVER_TIMESTAMP,
                }, merge=True)

        await asyncio.to_thread(lambda: _tx(fs.db.transaction()))

        # 4) 平台 SQL 库扣减库存
        async with async_session_factory() as session:
            for it in batch_items:
                pid, qty = it["product_id"], int(it["quantity"])
                await session.execute(
                    update(ShopProduct)
                    .where(ShopProduct.id == pid)
                    .values(stock=ShopProduct.stock - qty)
                )
            await session.commit()

        # 5) 同步余额（读 Firestore 再同步，确保是事务后的数值）
        try:
            wallet_doc = await fs.get(f"users/{uid}/store/wallet")
            from app.api.cms.services.wallet.wallet_secure_service import WalletSecureService
            await WalletSecureService._sync_balance(uid, float(wallet_doc.get("available_balance", 0.0)))
        except Exception as e:
            print(f"[WARN] 钱包同步失败: {e}")

        return PedroResponse.success(
            data={"batch_id": batch_id, "total_cost": total_cost, "count": len(batch_items)},
            msg="✅ 批量采购成功"
        )

    # ==============================================================
    # 📜 查询采购批次列表（返回原始 list，交给路由做分页）
    # ==============================================================
    @staticmethod
    async def list_purchase_batches(uid: str, limit: int = 20) -> list[dict]:
        """
        返回“原始列表”以便路由层组合 PedroResponse.page(...)
        Firestore 按 created_at 倒序
        会补齐 items[].product_detail（来自 SQL）
        """
        path = f"users/{uid}/store/meta/purchases"
        query = (
            fs_service.db.collection(path)
            .order_by("created_at", direction=firestore.Query.DESCENDING)  # ✅ 与写入字段一致
            .limit(limit)
        )
        docs = query.stream()
        batches = [doc.to_dict() for doc in docs if doc.exists]

        # 聚合商品 ID
        product_ids = set()
        for b in batches:
            for i in b.get("items", []):
                pid = i.get("product_id")
                if pid is not None:
                    product_ids.add(int(pid))

        # SQL 详情
        details_map = {}
        if product_ids:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(ShopProduct).options(
                        load_only(
                            ShopProduct.id,
                            ShopProduct.title,
                            ShopProduct.price,
                            ShopProduct.images,
                            ShopProduct.stock,
                            ShopProduct.rating,
                            ShopProduct.discount,
                        )
                    ).where(ShopProduct.id.in_(list(product_ids)))
                )
                products = result.scalars().all()
                details_map = {
                    int(p.id): {
                        "id": int(p.id),
                        "title": p.title,
                        "price": float(p.price),
                        "stock": int(p.stock or 0),
                        "images": getattr(p, "images", []),
                        "rating": getattr(p, "rating", None),
                        "discount": getattr(p, "discount", None),
                    }
                    for p in products
                }

        # 补齐详情
        for b in batches:
            for i in b.get("items", []):
                pid = int(i.get("product_id", 0))
                if pid in details_map:
                    i["product_detail"] = details_map[pid]

        return batches  # ✅ 注意：返回原始 list

    # ==============================================================
    # 🔍 查询单个采购详情（含 SQL 补全）
    # ==============================================================
    @staticmethod
    async def get_purchase_batch_detail(uid: str, batch_id: str):
        path = f"users/{uid}/store/meta/purchases/{batch_id}"
        batch = await fs.get(path)
        if not batch:
            return PedroResponse.fail(msg="采购批次不存在")

        items = batch.get("items", [])
        product_ids = [int(i["product_id"]) for i in items if i.get("product_id")]

        async with async_session_factory() as session:
            result = await session.execute(select(ShopProduct).where(ShopProduct.id.in_(product_ids)))
            products = {p.id: p for p in result.scalars().all()}

        for it in items:
            pid = int(it.get("product_id", 0))
            if pid in products:
                prod = products[pid]
                it["product_info"] = {
                    "id": prod.id,
                    "title": prod.title,
                    "price": float(prod.price),
                    "stock": prod.stock,
                }

        batch["items"] = items
        return PedroResponse.success(data=batch)

    # ==============================================================
    # 📜 查询需要进货的订单（返回原始 list，交给路由分页）
    # ==============================================================
    @staticmethod
    async def list_need_purchase_orders(uid: str, limit: int = 50) -> list[dict]:
        """
        查询所有 status == 'need_purchase' 的订单。
        若缺少 created_at 字段则自动回退到 __name__ 排序。
        """
        path = f"users/{uid}/store/meta/orders"
        col = fs_service.db.collection(path)

        try:
            query = (
                col.where("status", "==", "need_purchase")
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
            )
            docs = query.stream()
        except Exception as e:
            print(f"[WARN] Firestore 排序字段 created_at 不存在: {e}，使用 __name__ 回退。")
            query = (
                col.where("status", "==", "need_purchase")
                .order_by("__name__", direction=firestore.Query.DESCENDING)
                .limit(limit)
            )
            docs = query.stream()

        return [doc.to_dict() for doc in docs if doc.exists]

    # ==============================================================
    # 🏪 查询自己店铺详情
    # ==============================================================
    @staticmethod
    async def get_my_store(uid: str):
        """
        🏪 获取当前用户的店铺档案
        Firestore 路径: users/{uid}/store/profile
        """
        try:
            doc = await fs_service.get(f"users/{uid}/store/profile")
            if not doc:
                return PedroResponse.fail(msg="未找到店铺档案，请先开通店铺")
            return doc
        except Exception as e:
            print(f"[ERROR] 获取店铺信息失败: {e}")
            return PedroResponse.fail(msg="获取店铺信息失败")

    # ==============================================================
    # 💰 查询自己钱包余额
    # ==============================================================
    @staticmethod
    async def get_or_create_wallet(uid: str):
        """
        ✅ 获取钱包，如果不存在则自动创建一个空钱包
        Firestore 路径: users/{uid}/store/wallet
        """
        wallet_path = f"users/{uid}/store/wallet"

        try:
            # 1️⃣ 获取钱包文档（基于你的 async 封装）
            wallet_doc = await fs_service.get(wallet_path)

            # 2️⃣ 不存在 → 自动创建
            if not wallet_doc:
                default_wallet = {
                    "available_balance": 0.0,
                    "freeze": 0.0,
                    "currency": "USD",
                    "is_active": True,
                    "source": "system_auto",
                    "created_at": SERVER_TIMESTAMP,
                    "updated_at": SERVER_TIMESTAMP,
                    "last_txn": None,
                }

                await fs_service.set(wallet_path, default_wallet)
                print(f"[INFO] ✅ 为用户 {uid} 自动创建默认钱包")

                return PedroResponse.success(
                    data=default_wallet,
                    msg="✅ 钱包不存在，已自动创建空钱包"
                )

            # 3️⃣ 存在 → 直接返回
            return wallet_doc

        except Exception as e:
            print(f"[ERROR] 获取或创建钱包失败: {e}")
            return PedroResponse.fail(msg=f"❌ 钱包操作失败: {str(e)}")

    @staticmethod
    async def list_all_store_applications(
            status: str | None = None,
            keyword: str | None = None,
            page: int = 1,
            page_size: int = 20,
    ) -> PedroResponse:
        """
        🔍 查询所有用户的商铺申请（跨用户）
        Firestore 路径: users/{uid}/store/profile
        支持：
            - status: pending / verified / rejected
            - keyword: 支持匹配 store_name / email
            - page / page_size: 手动分页
        """

        # collection_group 能够跨所有用户目录查询 profile 文档
        query = fs_service.db.collection_group("store").order_by(
            "create_time", direction=firestore.Query.DESCENDING
        )

        if status:
            query = query.where("status", "==", status)

        # Firestore 不支持复杂模糊搜索，这里我们在客户端过滤 keyword
        docs = query.stream()
        all_docs = [doc.to_dict() for doc in docs if doc.id == "profile"]

        if keyword:
            keyword_lower = keyword.lower()
            all_docs = [
                d for d in all_docs
                if keyword_lower in str(d.get("store_name", "")).lower()
                or keyword_lower in str(d.get("email", "")).lower()
            ]

        total = len(all_docs)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = all_docs[start:end]


        return PedroResponse.page(
            items=page_items,
            total=total,
            page=page,
            size=page_size,
            msg="✅ 所有商家申请获取成功"
        )

