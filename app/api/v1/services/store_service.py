# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/13 20:15
# @Author  : Pedro
# @File    : merchant_service.py
# @Software: PyCharm
"""
import asyncio
import uuid
from typing import List, Dict, Any, Optional
from firebase_admin import firestore
from google.cloud.firestore_v1 import FieldFilter
from google.cloud.firestore_v1.field_path import FieldPath
from sqlalchemy import select, update
from sqlalchemy.orm import load_only

from app.api.cms.services.wallet.base_wallet_sync import BaseWalletSyncService
from app.api.v1.services.store.store_service_stats import StoreServiceStats
from app.extension.google_tools.firebase_admin_service import fs
from app.extension.google_tools.fs_transaction import SERVER_TIMESTAMP, fs_service, Increment
from app.api.v1.model.shop_product import ShopProduct
from app.pedro.db import async_session_factory
from app.api.cms.services.wallet.wallet_secure_service import WalletSecureService
from app.pedro.response import PedroResponse





class MerchantService:
    # ==============================================================
    # 🏪 创建商家档案 + 初始化统计 + 钱包
    # ==============================================================
    @staticmethod
    async def create_merchant(
        uid: str,
        name: str = None,
        email: str = None,
        address: str = None,
        logo: str = None,
        lang: str = None
    ):
        # ✅ 新增统计服务
        from app.api.v1.services.store.store_service_stats import StoreServiceStats
        from app.api.cms.services.store.merchant_service import FirestoreStoreService
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
            "created_at": SERVER_TIMESTAMP,
            "updated_at": SERVER_TIMESTAMP,
        }

        # Step 1️⃣ 创建 Firestore 商户档案
        store_ref.set(data, merge=True)
        print(f"✅ Firestore: Created merchant profile for user {uid}")

        # Step 2️⃣ 初始化 Firestore 统计信息
        try:
            FirestoreStoreService.init_store_stats(uid)
            await StoreServiceStats.full_sync(uid)
            print(f"✅ Firestore: Initialized store stats for {uid}")
        except Exception as e:
            print(f"[WARN] 初始化店铺统计信息失败: {e}")

        # Step 3️⃣ 自动创建钱包
        try:
            await MerchantService.get_or_create_wallet(uid)
        except Exception as e:
            print(f"[WARN] 自动创建钱包失败: {e}")

        return PedroResponse.success(msg="✅ 申请开通店铺成功")

    # ==============================================================
    # 💰 获取或创建钱包
    # ==============================================================
    @staticmethod
    async def get_or_create_wallet(uid: str):
        wallet_path = f"users/{uid}/store/wallet"
        try:
            wallet_doc = await fs_service.get(wallet_path)
            if not wallet_doc:
                default_wallet = {
                    "available_balance": 0.0,
                    "freeze": 0.0,
                    "currency": "USD",
                    "is_active": True,
                    "source": "system_auto",
                    "last_txn": None,
                }
                await fs_service.set(wallet_path, default_wallet)
                print(f"[INFO] ✅ 为用户 {uid} 自动创建默认钱包")
                return PedroResponse.success(data=default_wallet, msg="✅ 钱包不存在，已自动创建空钱包")
            return wallet_doc
        except Exception as e:
            print(f"[ERROR] 获取或创建钱包失败: {e}")
            return PedroResponse.fail(msg=f"❌ 钱包操作失败: {str(e)}")

    # ==============================================================
    # 📦 批量采购（兼容异步事务）
    # ==============================================================
    @staticmethod
    async def purchase_batch(uid: str, items: list[dict[str, int]]) -> PedroResponse:
        # Step 1️⃣ 从 SQL 读取商品信息
        async with async_session_factory() as session:
            ids = [int(i["product_id"]) for i in items]
            result = await session.execute(select(ShopProduct).where(ShopProduct.id.in_(ids)))
            products = {int(p.id): p for p in result.scalars().all()}

        # Step 2️⃣ 计算总价
        batch_items, total_cost = [], 0.0
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

        batch_id = uuid.uuid4().hex
        purchase_ref = fs.db.document(f"users/{uid}/store/meta/purchases/{batch_id}")

        # Step 3️⃣ Firestore 事务（在同步线程中执行）
        def run_transaction():
            transaction = fs.db.transaction()
            wallet_ref = fs.db.document(f"users/{uid}/store/wallet")

            snap = wallet_ref.get(transaction=transaction)
            balance = float((snap.to_dict() or {}).get("available_balance", 0.0))
            if balance < total_cost:
                raise ValueError(f"余额不足：{balance:.2f} < {total_cost:.2f}")

            # 扣款
            transaction.update(wallet_ref, {
                "available_balance": Increment(-total_cost),
                "updated_at": SERVER_TIMESTAMP,
            })

            # 写采购记录
            transaction.set(purchase_ref, {
                "batch_id": batch_id,
                "items": batch_items,
                "total_amount": total_cost,
                "status": "purchased",
                "created_at": SERVER_TIMESTAMP,
            })

            # 累加商户库存
            for it in batch_items:
                pid, qty = it["product_id"], int(it["quantity"])
                product_ref = fs.db.document(f"users/{uid}/store/meta/products/{pid}")
                transaction.set(product_ref, {
                    "product_id": pid,
                    "title": it["product_name"],
                    "stock": Increment(qty),
                    "merchant_price": it["unit_price"],
                    "updated_at": SERVER_TIMESTAMP,
                }, merge=True)

            transaction.commit()

        # ✅ 在线程中运行同步 Firestore 事务
        await asyncio.to_thread(run_transaction)

        # Step 4️⃣ SQL 扣库存
        async with async_session_factory() as session:
            for it in batch_items:
                pid, qty = it["product_id"], int(it["quantity"])
                await session.execute(
                    update(ShopProduct)
                    .where(ShopProduct.id == pid)
                    .values(stock=ShopProduct.stock - qty)
                )
            await session.commit()

        # Step 5️⃣ 同步余额与统计
        try:
            wallet_doc = await fs.get(f"users/{uid}/store/wallet")
            await BaseWalletSyncService.sync_all(uid, float(wallet_doc.get("available_balance", 0.0)))
            await StoreServiceStats.full_sync(uid)
        except Exception as e:
            print(f"[WARN] 同步钱包或统计失败: {e}")

        return PedroResponse.success(
            data={"batch_id": batch_id, "total_cost": total_cost, "count": len(batch_items)},
            msg="✅ 批量采购成功"
        )

    # ==============================================================
    # 🏪 查询自己店铺
    # ==============================================================
    @staticmethod
    async def get_my_store(uid: str):
        try:
            doc = await fs_service.get(f"users/{uid}/store/profile")
            if not doc:
                return PedroResponse.fail(msg="未找到店铺档案，请先开通店铺")
            return doc
        except Exception as e:
            print(f"[ERROR] 获取店铺信息失败: {e}")
            return PedroResponse.fail(msg="获取店铺信息失败")

        # ==============================================================
        # 📜 查询采购批次列表（含 SQL 商品补全 + created_at 排序）
        # ==============================================================

    @staticmethod
    async def list_purchase_batches(uid: str, limit: int = 20, start_after: str | None = None):
        """
        🔍 获取商户的采购批次列表
        Firestore 路径: users/{uid}/store/meta/purchases/{batch_id}

        每个批次文档结构:
        {
          "batch_id": "uuid",
          "items": [ {product_id, product_name, quantity, unit_price, subtotal}, ... ],
          "total_amount": 123.45,
          "status": "purchased",
          "created_at": timestamp
        }

        Args:
            uid (str): 用户 id 或 uuid（自动兼容）
            limit (int): 每页条数
            start_after (str | None): 上一页最后一条 ID
        """

        try:
            # ✅ 统一 Firestore 路径
            from app.pedro.id_helper import IDHelper
            uid = IDHelper.safe_uid(uid)
            path = f"users/{uid}/store/meta/purchases"

            # ✅ 构建 Firestore 查询
            query = (
                fs_service.db.collection(path)
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
            )

            # ✅ 分页支持
            if start_after:
                start_doc = fs_service.db.document(f"{path}/{start_after}")
                query = query.start_after(start_doc)

            # ✅ 异步读取文档
            docs = await fs_service.list_documents(path)
            batches = [doc.to_dict() for doc in docs if doc.exists]

            if not batches:
                return PedroResponse.success(
                    data={"items": [], "count": 0},
                    msg="⚠️ 当前没有采购批次记录"
                )

            # ✅ 聚合所有 product_id
            product_ids = set()
            for b in batches:
                for i in b.get("items", []):
                    pid = i.get("product_id")
                    if pid is not None:
                        product_ids.add(int(pid))

            # ✅ 批量获取 SQL 商品信息
            product_map = {}
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
                                ShopProduct.discount,
                                ShopProduct.rating,
                                ShopProduct.thumbnail
                            )
                        ).where(ShopProduct.id.in_(list(product_ids)))
                    )
                    for p in result.scalars().all():
                        product_map[int(p.id)] = {
                            "id": int(p.id),
                            "title": p.title,
                            "price": float(p.price or 0.0),
                            "stock": int(p.stock or 0),
                            "rating": float(p.rating or 0.0),
                            "discount": float(p.discount or 0.0),
                            "images": p.images or [],
                            "thumbnail": p.thumbnail or None
                        }

            # ✅ 商品详情补全
            for b in batches:
                for i in b.get("items", []):
                    pid = int(i.get("product_id", 0))
                    if pid in product_map:
                        i["product_detail"] = product_map[pid]

            # ✅ 时间排序（确保有序）
            batches.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
            batches = batches[:limit]

            return PedroResponse.success(
                data={
                    "items": batches,
                    "count": len(batches),
                    "next_page_token": batches[-1].get("batch_id") if batches else None,
                },
                msg=f"✅ 成功获取 {len(batches)} 条采购批次记录"
            )

        except Exception as e:
            print(f"[ERROR] list_purchase_batches 失败: {e}")
            return PedroResponse.fail(msg=f"❌ 查询失败: {e}")


    # ==============================================================
    # 🔍 查询需要进货的订单（分页 + 容错 + 路径自动识别）
    # ==============================================================
    @staticmethod
    async def list_need_purchase_orders(uid: str, limit: int = 50, start_after: str | None = None):
        try:
            from app.pedro.id_helper import IDHelper
            uid = IDHelper.safe_uid(uid)
            path = f"users/{uid}/store/meta/orders"
            col_ref = fs_service.db.collection(path)

            query = col_ref.where(filter=FieldFilter("status", "==", "need_purchase"))

            try:
                query = query.order_by("created_at", direction=firestore.firestore.Query.DESCENDING)
            except Exception:
                query = query.order_by("__name__", direction=firestore.firestore.Query.DESCENDING)

            if start_after:
                last_doc = fs_service.db.document(f"{path}/{start_after}")
                query = query.start_after(last_doc)

            query = query.limit(limit)

            # ① 获取 Firestore 订单文档
            docs = await fs_service.list_documents(path)

            raw_orders = []
            for d in docs:
                data = d.to_dict()
                if not data or data.get("status") != "need_purchase":
                    continue

                raw_orders.append({
                    "id": d.id,
                    "order_no": data.get("order_id"),
                    "status": data.get("status"),
                    "created_at": data.get("created_at"),
                    "total_amount": data.get("total_amount", 0),
                    "buyer_info": {
                        "address": data.get("buyer_address",""),
                        "city": data.get("buyer_region",""),
                        "email": data.get("buyer_email_masked",""),
                        "name": data.get("buyer_name",""),
                    },
                    "items": data.get("items", []),  # 直接使用 firestore 中的商品详情
                })

            raw_orders.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
            raw_orders = raw_orders[:limit]

            return PedroResponse.success(
                data={
                    "items": raw_orders,
                    "count": len(raw_orders),
                    "next_page_token": raw_orders[-1]["id"] if raw_orders else None
                },
                msg=f"成功获取 {len(raw_orders)} 条待进货订单"
            )

        except Exception as e:
            print(f"[ERROR] list_need_purchase_orders 失败: {e}")
            return PedroResponse.fail(msg=f"❌ 查询失败: {e}")

    @staticmethod
    async def list_all_store_applications(
            *,
            status: Optional[str] = None,
            keyword: Optional[str] = None,
            page: int = 1,
            page_size: int = 20,
    ) -> PedroResponse:
        """
        🔍 查询所有店铺申请
        Firestore 路径：users/{uid}/store/profile
        """
        try:
            # ✅ 跨所有用户目录查询 store 下的文档
            query = fs_service.db.collection_group("store").order_by(
                "created_at", direction=firestore.firestore.Query.DESCENDING
            )

            # ✅ 按状态过滤
            if status:
                query = query.where("status", "==", status)

            # ✅ 拉取所有文档
            docs = query.stream()
            all_docs = [doc.to_dict() for doc in docs if doc.id == "profile"]

            # ✅ 客户端关键字过滤
            if keyword:
                keyword_lower = keyword.lower()
                all_docs = [
                    d for d in all_docs
                    if keyword_lower in str(d.get("store_name", "")).lower()
                       or keyword_lower in str(d.get("email", "")).lower()
                       or keyword_lower in str(d.get("address", "")).lower()
                ]

            # ✅ 排序 + 分页
            total = len(all_docs)
            start = (page - 1) * page_size
            end = start + page_size
            items = all_docs[start:end]

            # ✅ 格式化结果
            formatted = []
            for d in items:
                formatted.append({
                    "store_name": d.get("store_name"),
                    "email": d.get("email"),
                    "status": d.get("status", "pending"),
                    "verify_badge": d.get("verify_badge", False),
                    "level": d.get("level", "bronze"),
                    "address": d.get("address"),
                    "lang": d.get("lang", "en"),
                    "logo": d.get("logo"),
                    "create_time": d.get("created_at"),
                    "update_time": d.get("updated_at"),
                })

            return PedroResponse.page(
                items=formatted,
                total=total,
                page=page,
                size=page_size,
                msg="✅ 店铺申请列表获取成功"
            )

        except Exception as e:
            print(f"[ERROR] list_all_store_applications failed: {e}")
            return PedroResponse.fail(msg=f"❌ 查询失败: {e}")

