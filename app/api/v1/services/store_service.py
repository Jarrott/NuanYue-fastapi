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
from google.cloud.firestore_v1 import FieldFilter, transactional
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
from app.pedro.id_helper import IDHelper
from app.pedro.response import PedroResponse


# ==============================================================
# 🔥 Firestore Compatibility Patch
# 修复 fs.db 丢失 / transaction 不兼容问题（无需修改旧代码）
# ==============================================================

try:
    _firestore_db = firestore.client()

    if not hasattr(fs, "db"):
        fs.db = _firestore_db

    if not hasattr(fs, "transaction"):
        fs.transaction = _firestore_db.transaction

    print("✔ Firestore Compatibility Patch Applied (fs.db + transaction restored)")

except Exception as e:
    print(f"[WARN] Firestore compatibility patch failed: {e}")


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

        store_ref.set(data, merge=True)

        print(f"✅ Firestore: Created merchant profile for user {uid}")

        # 初始化 Firestore 统计
        try:
            FirestoreStoreService.init_store_stats(uid)
            await StoreServiceStats.full_sync(uid)
        except Exception as e:
            print(f"[WARN] 初始化店铺统计失败: {e}")

        # 自动创建钱包
        try:
            await MerchantService.get_or_create_wallet(uid)
        except Exception as e:
            print(f"[WARN] 自动创建钱包失败: {e}")

        return PedroResponse.success(msg="✅ 店铺申请成功")

    # ==============================================================
    # 💰 获取或创建钱包
    # ==============================================================
    @staticmethod
    async def get_or_create_wallet(uid: str):
        wallet_path = f"users/{uid}/store/wallet"

        try:
            wallet_doc = await fs_service.get(wallet_path)

            # 关键：如果存在但缺少字段，也要补全保证事务能读取
            default_wallet = {
                "available_balance": 0.0,
                "freeze": 0.0,
                "currency": "USD",
                "is_active": True,
                "source": "system_auto",
                "last_txn": None,
                "created_at": SERVER_TIMESTAMP,
                "updated_at": SERVER_TIMESTAMP
            }

            if not wallet_doc:
                await fs_service.set(wallet_path, default_wallet)
                print(f"[INFO] 创建钱包成功 → {uid}")
                return default_wallet

            # 🔥 如果文档存在但是字段不完整（你现在的情况）
            patched = False
            for k, v in default_wallet.items():
                if k not in wallet_doc:
                    wallet_doc[k] = v
                    patched = True

            if patched:
                await fs_service.update(wallet_path, wallet_doc)
                print("[FIX] 钱包结构被自动修复")

            return wallet_doc

        except Exception as e:
            print(f"[ERROR] get_or_create_wallet failed: {e}")
            return PedroResponse.fail(msg=f"❌ 钱包初始化失败: {str(e)}")

    # ==============================================================
    # 📦 批量采购（含 Firestore 事务）
    # ==============================================================
    @staticmethod
    async def purchase_batch(uid: str, items: list[dict[str, int]]) -> PedroResponse:
        uid = IDHelper.safe_uid(uid)  # 🔥 强制转换为 Firestore UID
        print("=================================================",uid)
        # Step 1️⃣ SQL 读取商品
        async with async_session_factory() as session:
            ids = [int(i["product_id"]) for i in items]
            result = await session.execute(select(ShopProduct).where(ShopProduct.id.in_(ids)))
            products = {int(p.id): p for p in result.scalars().all()}

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
            return PedroResponse.fail(msg="总价异常")

        batch_id = uuid.uuid4().hex

        wallet_ref = fs.document(f"users/{uid}/store/wallet")
        purchase_ref = fs.document(f"users/{uid}/store/meta/purchases/{batch_id}")

        @transactional
        def commit_transaction(transaction):
            # 💰 读取余额
            snap = wallet_ref.get(transaction=transaction)
            balance = float((snap.to_dict() or {}).get("available_balance", 0.0))

            if balance < total_cost:
                raise ValueError(f"余额不足: {balance:.2f} < {total_cost:.2f}")

            # 扣款
            transaction.update(wallet_ref, {
                "available_balance": Increment(-total_cost),
                "updated_at": SERVER_TIMESTAMP,
            })

            # 写采购单
            transaction.set(purchase_ref, {
                "batch_id": batch_id,
                "items": batch_items,
                "total_amount": total_cost,
                "status": "purchased",
                "created_at": SERVER_TIMESTAMP,
            })

            # 更新库存
            for it in batch_items:
                pid, qty = it["product_id"], int(it["quantity"])
                product_ref = fs.document(f"users/{uid}/store/meta/products/{pid}")
                transaction.set(product_ref, {
                    "product_id": pid,
                    "title": it["product_name"],
                    "stock": Increment(qty),
                    "merchant_price": it["unit_price"],
                    "updated_at": SERVER_TIMESTAMP,
                }, merge=True)

        # 🔥 同步事务执行（不会阻塞 async）
        await asyncio.to_thread(commit_transaction, firestore.client().transaction())

        # Step 4️⃣ SQL库存更新
        async with async_session_factory() as session:
            for it in batch_items:
                pid, qty = it["product_id"], int(it["quantity"])
                await session.execute(
                    update(ShopProduct)
                    .where(ShopProduct.id == pid)
                    .values(stock=ShopProduct.stock - qty)
                )
            await session.commit()

        # Step 5️⃣ 同步更新钱包缓存和统计
        wallet_doc = await fs_service.get(f"users/{uid}/store/wallet")
        await BaseWalletSyncService.sync_all(uid, float(wallet_doc.get("available_balance", 0.0)))
        await StoreServiceStats.full_sync(uid)

        return PedroResponse.success(
            data={"batch_id": batch_id, "total_cost": total_cost, "count": len(batch_items)},
            msg="采购成功"
        )

    # ==============================================================
    # 🏪 查询自己店铺
    # ==============================================================
    @staticmethod
    async def get_my_store(uid: str):
        try:
            doc = await fs_service.get(f"users/{uid}/store/profile")
            if not doc:
                return PedroResponse.fail(msg="未找到店铺")
            return doc
        except Exception as e:
            return PedroResponse.fail(msg=f"获取失败: {e}")

    # ==============================================================
    # 📜 查询采购批次列表（分页）
    # ==============================================================
    @staticmethod
    async def list_purchase_batches(uid: str, limit: int = 20, start_after: str | None = None):
        try:
            path = f"users/{uid}/store/meta/purchases"
            docs = await fs_service.list_documents(path)

            batches = [doc.to_dict() for doc in docs if doc.exists]

            if not batches:
                return PedroResponse.success(data={"items": [], "count": 0}, msg="暂无记录")

            product_ids = set()
            for b in batches:
                for i in b.get("items", []):
                    pid = i.get("product_id")
                    if pid:
                        product_ids.add(int(pid))

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
                            "price": float(p.price or 0),
                            "stock": int(p.stock or 0),
                            "rating": float(p.rating or 0),
                            "discount": float(p.discount or 0),
                            "images": p.images or [],
                            "thumbnail": p.thumbnail
                        }

            for b in batches:
                for i in b.get("items", []):
                    pid = int(i.get("product_id", 0))
                    if pid in product_map:
                        i["product_detail"] = product_map[pid]

            batches.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
            batches = batches[:limit]

            return PedroResponse.success(
                data={
                    "items": batches,
                    "count": len(batches),
                    "next_page_token": batches[-1].get("batch_id") if batches else None,
                },
                msg=f"获取 {len(batches)} 条记录成功"
            )

        except Exception as e:
            return PedroResponse.fail(msg=f"查询失败: {e}")

    # ==============================================================
    # 🔍 查询需要采购订单
    # ==============================================================
    @staticmethod
    async def list_need_purchase_orders(uid: str, limit: int = 50, start_after: str | None = None):
        try:
            path = f"users/{uid}/store/meta/orders"
            docs = await fs_service.list_documents(path)

            orders = []
            for d in docs:
                data = d.to_dict()
                if data and data.get("status") == "need_purchase":
                    orders.append({
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
                        "items": data.get("items", [])
                    })

            orders.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
            orders = orders[:limit]

            return PedroResponse.success(
                data={
                    "items": orders,
                    "count": len(orders),
                    "next_page_token": orders[-1]["id"] if orders else None
                },
                msg=f"成功获取 {len(orders)} 条订单"
            )

        except Exception as e:
            return PedroResponse.fail(msg=f"查询失败: {e}")

    # ==============================================================
    # 🧾 查询所有店铺申请
    # ==============================================================
    @staticmethod
    async def list_all_store_applications(
        *,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PedroResponse:

        try:
            query = fs_service.db.collection_group("store").order_by(
                "created_at", direction=firestore.firestore.Query.DESCENDING
            )

            if status:
                query = query.where("status", "==", status)

            docs = query.stream()
            all_docs = [doc.to_dict() for doc in docs if doc.id == "profile"]

            if keyword:
                keyword_lower = keyword.lower()
                all_docs = [
                    d for d in all_docs
                    if keyword_lower in str(d.get("store_name", "")).lower()
                       or keyword_lower in str(d.get("email", "")).lower()
                       or keyword_lower in str(d.get("address", "")).lower()
                ]

            total = len(all_docs)
            start = (page - 1) * page_size
            end = start + page_size

            items = all_docs[start:end]

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
                msg="查询成功"
            )

        except Exception as e:
            return PedroResponse.fail(msg=f"查询失败: {e}")
