# @Time    : 2025/11/10 03:40
# @Author  : Pedro
# @File    : merchant_service.py
# @Software: PyCharm
"""
🔥 Pedro-Core MerchantService
商户核心服务模块（钱包 + 店铺采购）
功能包含：
  ✅ 批量采购（Firestore + PostgreSQL 同步）
  ✅ 钱包扣款与余额同步
  ✅ 查询采购记录（列表 / 详情）
  ✅ 整合 Firestore 与 SQL 商品信息
"""

import asyncio
import uuid
from typing import List, Dict, Any
from firebase_admin.firestore import firestore
from sqlalchemy import select, update
from sqlalchemy.orm import load_only

from app.extension.google_tools.firestore import fs_service as fs
from app.api.v1.model.shop_product import ShopProduct
from app.pedro.db import async_session_factory
from app.api.cms.services.wallet.wallet_secure_service import WalletSecureService
from app.pedro.response import PedroResponse


class MerchantService:
    # ==============================================================
    # 📦 批量采购（含 Firestore 事务 + SQL 库同步 + 钱包扣款）
    # ==============================================================
    @staticmethod
    async def purchase_batch(uid: str, items: list[dict[str, int]]) -> PedroResponse:
        """
        商户批量采购接口
        1️⃣ 检查 PostgreSQL 商品库存
        2️⃣ Firestore 事务：扣余额 + 写采购记录 + 增加商家库存
        3️⃣ SQL 库扣减平台库存
        4️⃣ 钱包余额同步
        """
        # 1️⃣ 查询数据库内商品信息
        async with async_session_factory() as session:
            ids = [i["product_id"] for i in items]
            result = await session.execute(select(ShopProduct).where(ShopProduct.id.in_(ids)))
            products = {p.id: p for p in result.scalars().all()}

        # 2️⃣ 计算总价并验证余额
        total_cost = sum(float(products[i["product_id"]].price) * i["quantity"] for i in items)
        wallet = await fs.get(f"users/{uid}/store/wallet")
        if wallet.get("available_balance", 0) < total_cost:
            return PedroResponse.fail(msg=f"余额不足，总价 {total_cost} USD")

        batch_id = f"BATCH-{uuid.uuid4().hex[:10]}"

        # 3️⃣ Firestore 事务执行
        @firestore.transactional
        def _tx(transaction):
            wallet_ref = fs.db.document(f"users/{uid}/store/wallet")
            snap = wallet_ref.get(transaction=transaction)
            balance = (snap.to_dict() or {}).get("available_balance", 0)
            if balance < total_cost:
                raise ValueError(f"余额不足：需要 {total_cost} USD，当前余额 {balance}")

            # 更新钱包余额
            transaction.update(wallet_ref, {
                "available_balance": firestore.Increment(-total_cost),
                "updated_at": firestore.SERVER_TIMESTAMP,
            })

            # 写入每个商品采购记录
            for item in items:
                pid, qty = item["product_id"], item["quantity"]
                p = products[pid]
                sub_id = f"{batch_id}-{pid}"

                purchase_ref = fs.db.document(f"users/{uid}/store/meta/purchases/{sub_id}")
                product_ref = fs.db.document(f"users/{uid}/store/meta/products/{pid}")
                log_ref = fs.db.document(f"users/{uid}/store/logs/meta/{sub_id}")

                transaction.set(purchase_ref, {
                    "purchase_id": sub_id,
                    "product_id": pid,
                    "title": p.title,
                    "quantity": qty,
                    "unit_price": float(p.price),
                    "total_cost": float(p.price) * qty,
                    "timestamp": firestore.SERVER_TIMESTAMP,
                })
                transaction.set(product_ref, {
                    "product_id": pid,
                    "stock": firestore.Increment(qty),
                    "merchant_price": float(p.price) * 1.15,
                    "platform_price": float(p.price),
                    "status": "active",
                    "updated_at": firestore.SERVER_TIMESTAMP,
                }, merge=True)
                transaction.set(log_ref, {
                    "type": "batch_purchase",
                    "desc": f"批量采购 {p.title} × {qty}",
                    "amount": -float(p.price) * qty,
                    "timestamp": firestore.SERVER_TIMESTAMP,
                })

        # ✅ Firestore 事务提交
        await asyncio.to_thread(lambda: _tx(fs.db.transaction()))

        # 4️⃣ 更新 SQL 平台库存
        async with async_session_factory() as session:
            ids = [it["product_id"] for it in items]
            result = await session.execute(
                select(ShopProduct.id, ShopProduct.title, ShopProduct.stock)
                .where(ShopProduct.id.in_(ids))
            )
            products = {p.id: p for p in result.mappings().all()}

            insufficient = []
            for it in items:
                pid, qty = it["product_id"], int(it["quantity"])
                product = products.get(pid)
                if not product:
                    insufficient.append(f"商品ID {pid} 不存在")
                elif product["stock"] < qty:
                    insufficient.append(
                        f"商品ID:{product['id']}|{product['title']} 库存不足（剩余 {product['stock']}）"
                    )
            if insufficient:
                return PedroResponse.fail(msg=f"库存不足：{'、'.join(insufficient)}")

            # 扣减库存
            for it in items:
                pid, qty = it["product_id"], int(it["quantity"])
                await session.execute(
                    update(ShopProduct)
                    .where(ShopProduct.id == pid)
                    .values(stock=ShopProduct.stock - qty)
                )
            await session.commit()

        # 5️⃣ 同步钱包余额
        try:
            wallet = await fs.get(f"users/{uid}/store/wallet")
            balance_after = float(wallet.get("available_balance", 0))
            await WalletSecureService._sync_balance(uid, balance_after)
        except Exception as e:
            print(f"[WARN] 余额同步失败: {e}")

        return PedroResponse.success(data={
            "batch_id": batch_id,
            "total_cost": total_cost,
            "count": len(items),
            "msg": "✅ 批量采购成功"
        })

    # ==============================================================
    # 📜 查询采购批次列表（Firestore + SQL 联合）
    # ==============================================================
    @staticmethod
    async def list_purchase_batches(uid: str, limit: int = 20):
        """
        获取商户采购记录列表，补齐 SQL 商品详情。
        """
        path = f"users/{uid}/store/meta/purchases"
        query = fs.db.collection(path).order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit)
        docs = query.stream()
        purchase_list = [doc.to_dict() for doc in docs]

        product_ids = list({p.get("product_id") for p in purchase_list if p.get("product_id")})
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
                    ).where(ShopProduct.id.in_(product_ids))
                )
                products = result.scalars().all()
                details_map = {
                    p.id: getattr(p, "to_dict", lambda: {
                        "id": p.id,
                        "title": p.title,
                        "price": float(p.price),
                        "stock": p.stock
                    })()
                    for p in products
                }

        # 🔗 合并 Firestore 与 SQL 商品详情
        for p in purchase_list:
            pid = p.get("product_id")
            if pid and pid in details_map:
                p["product_detail"] = details_map[pid]

        return PedroResponse.success(
            data={"count": len(purchase_list), "purchases": purchase_list},
            msg=f"✅ 获取采购记录成功，共 {len(purchase_list)} 条"
        )

    # ==============================================================
    # 🔍 查询单个采购详情
    # ==============================================================
    @staticmethod
    async def get_purchase_batch_detail(uid: str, batch_id: str):
        path = f"users/{uid}/store/meta/purchases/{batch_id}"
        data = await fs.get(path)
        if not data:
            return PedroResponse.fail(msg="采购批次不存在")
        return PedroResponse.success(data=data)

    # ==============================================================
    # 🧾 Firestore + SQL 整合（含商品详情）
    # ==============================================================
    @staticmethod
    async def get_purchase_batch_with_products(uid: str, batch_id: str):
        path = f"users/{uid}/store/meta/purchases/{batch_id}"
        batch = await fs.get(path)
        if not batch:
            return PedroResponse.fail(msg="采购记录不存在")

        items = batch.get("items", [])
        product_ids = [i["product_id"] for i in items]

        async with async_session_factory() as session:
            result = await session.execute(select(ShopProduct).where(ShopProduct.id.in_(product_ids)))
            products = {p.id: p for p in result.scalars().all()}

        enriched = []
        for item in items:
            pid = item["product_id"]
            prod = products.get(pid)
            enriched.append({
                **item,
                "product_info": prod.to_dict() if prod and hasattr(prod, "to_dict") else None
            })

        batch["items"] = enriched
        return PedroResponse.success(data=batch)
