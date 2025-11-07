# @Time    : 2025/11/7 23:59
# @Author  : Pedro
# @File    : merchant_service.py
# @Software: PyCharm
"""
🔥 商家服务统一模块（钱包 + 店铺 + 采购）
整合所有商家行为：
  - 店铺创建 / 语言设置
  - 钱包操作（读取、加钱、提现）
  - 采购单商品 / 批量采购
  - Firestore 日志自动记录
"""
import asyncio
import time
import uuid
from typing import Dict, Any, List
from firebase_admin.firestore import firestore
from sqlalchemy import select, update

from app.api.cms.services.wallet.wallet_secure_service import WalletSecureService
from app.pedro.response import PedroResponse
from app.pedro.db import async_session_factory
from app.api.v1.model.shop_product import ShopProduct
from app.extension.google_tools.firestore import fs_service as fs


class MerchantService:
    # ==============================================================
    # 🔹 获取店铺资料
    # ==============================================================
    @staticmethod
    async def get_profile(uid: str) -> Dict[str, Any]:
        profile = await fs.get(f"users/{uid}/store/profile")
        if not profile:
            profile = {
                "store_name": "未命名店铺",
                "avatar": None,
                "verify_badge": False,
                "level": "bronze",
                "email": None,
                "lang": "en",
            }
            await fs.set(f"users/{uid}/store/profile", profile, merge=True)
        return profile

    # ==============================================================
    # 💰 钱包读取
    # ==============================================================
    @staticmethod
    async def get_wallet(uid: str) -> Dict[str, Any]:
        wallet = await fs.get(f"users/{uid}/store/wallet")
        if not wallet:
            wallet = {
                "available_balance": 0,
                "frozen_balance": 0,
                "pending_payout": 0,
                "currency": "USD",
            }
            await fs.set(f"users/{uid}/store/wallet", wallet, merge=True)
        return wallet

    # ==============================================================
    # 🧾 增加利润（订单完成后）
    # ==============================================================
    @staticmethod
    async def add_profit(uid: str, amount: float, order_id: str, desc: str = "订单收益"):
        """
        💰 商家利润增加（调用 WalletSecureService）
        - Firestore + Ledger + SQL + RTDB 自动处理
        - MerchantService 只做业务封装
        """
        reference = f"order:{order_id}"

        result = await WalletSecureService.credit_wallet(
            uid=uid,
            amount=amount,
            reference=reference,
            source="order",
            desc=desc,
            operator="system"
        )

        return PedroResponse.success(
            msg=f"订单 {order_id} 收益 {amount} USD 已入账",
            data=result.data if hasattr(result, "data") else result
        )

    # ==============================================================
    # 🏪 创建店铺
    # ==============================================================
    @staticmethod
    async def create_merchant(uid: str, name: str | None = None,
                              email: str | None = None,
                              address: str | None = None,
                              logo: str | None = None) -> Dict[str, Any]:
        store_id = uuid.uuid4().hex[:12]
        log_id = f"init-{int(time.time())}"

        profile_data = {
            "store_id": store_id,
            "store_name": name or f"Store-{store_id[:6]}",
            "avatar": logo,
            "verify_badge": False,
            "level": "bronze",
            "status": "pending",
            "address": address,
            "email": email,
            "lang": "en",
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP
        }

        wallet_data = {
            "available_balance": 0,
            "frozen_balance": 0,
            "pending_payout": 0,
            "currency": "USD",
            "created_at": firestore.SERVER_TIMESTAMP
        }

        await fs.set(f"users/{uid}/store/profile", profile_data, merge=False)
        await fs.set(f"users/{uid}/store/wallet", wallet_data, merge=False)

        await fs.set(f"users/{uid}/store/logs/{log_id}", {
            "type": "merchant_created",
            "desc": f"初始化店铺 {profile_data['store_name']}",
            "timestamp": firestore.SERVER_TIMESTAMP,
        }, merge=False)

        return {"store_id": store_id, "status": "pending"}

    # ==============================================================
    # 🛒 单商品采购
    # ==============================================================
    @staticmethod
    async def purchase_single(uid: str, product_id: int, quantity: int):
        async with async_session_factory() as session:
            result = await session.execute(select(ShopProduct).where(ShopProduct.id == product_id))
            product = result.scalar_one_or_none()
            if not product:
                return PedroResponse.fail(msg="商品不存在")
            if product.stock < quantity:
                return PedroResponse.fail(msg="平台库存不足")

            total_cost = float(product.price) * quantity

        wallet = await MerchantService.get_wallet(uid)
        if wallet.get("available_balance", 0) < total_cost:
            return PedroResponse.fail(msg=f"余额不足，需 {total_cost} USD")

        purchase_id = f"PCH-{uuid.uuid4().hex[:10]}"
        wallet_path = f"users/{uid}/store/wallet"
        purchase_path = f"users/{uid}/store/purchases/{purchase_id}"
        product_path = f"users/{uid}/store/products/{product_id}"
        log_path = f"users/{uid}/store/logs/{purchase_id}"

        def _tx(transaction):
            wallet_ref = fs.db.document(wallet_path)
            snapshot = wallet_ref.get(transaction=transaction)
            balance = snapshot.to_dict().get("available_balance", 0)
            if balance < total_cost:
                raise ValueError("余额不足")

            transaction.update(wallet_ref, {
                "available_balance": firestore.Increment(-total_cost),
                "updated_at": firestore.SERVER_TIMESTAMP,
            })
            transaction.set(fs.db.document(purchase_path), {
                "purchase_id": purchase_id,
                "product_id": product_id,
                "title": product.title,
                "quantity": quantity,
                "unit_price": float(product.price),
                "total_cost": total_cost,
                "timestamp": firestore.SERVER_TIMESTAMP,
            })
            transaction.set(fs.db.document(product_path), {
                "product_id": product_id,
                "stock": firestore.Increment(quantity),
                "merchant_price": float(product.price) * 1.15,
                "platform_price": float(product.price),
                "status": "active",
                "updated_at": firestore.SERVER_TIMESTAMP,
            }, merge=True)
            transaction.set(fs.db.document(log_path), {
                "type": "purchase",
                "desc": f"采购 {product.title} × {quantity}",
                "amount": -total_cost,
                "timestamp": firestore.SERVER_TIMESTAMP,
            })

        await asyncio.to_thread(lambda: fs.db.run_transaction(_tx))

        async with async_session_factory() as session:
            await session.execute(
                update(ShopProduct)
                .where(ShopProduct.id == product_id)
                .values(stock=product.stock - quantity)
            )
            await session.commit()

        return PedroResponse.success(data={
            "purchase_id": purchase_id,
            "total_cost": total_cost,
            "msg": "采购成功"
        })

    # ==============================================================
    # 📦 批量采购
    # ==============================================================
    @staticmethod
    async def purchase_batch(uid: str, items: List[Dict[str, int]]):
        async with async_session_factory() as session:
            ids = [i["product_id"] for i in items]
            result = await session.execute(select(ShopProduct).where(ShopProduct.id.in_(ids)))
            products = {p.id: p for p in result.scalars().all()}

        total_cost = sum(float(products[i["product_id"]].price) * i["quantity"] for i in items)
        wallet = await MerchantService.get_wallet(uid)
        if wallet.get("available_balance", 0) < total_cost:
            return PedroResponse.fail(msg=f"余额不足，总价 {total_cost} USD")

        batch = fs.db.batch()
        wallet_ref = fs.db.document(f"users/{uid}/store/wallet")
        batch.update(wallet_ref, {
            "available_balance": firestore.Increment(-total_cost),
            "updated_at": firestore.SERVER_TIMESTAMP,
        })

        batch_id = f"BATCH-{uuid.uuid4().hex[:10]}"
        for item in items:
            pid, qty = item["product_id"], item["quantity"]
            p = products[pid]
            sub_id = f"{batch_id}-{pid}"
            purchase_ref = fs.db.document(f"users/{uid}/store/purchases/{sub_id}")
            product_ref = fs.db.document(f"users/{uid}/store/products/{pid}")
            log_ref = fs.db.document(f"users/{uid}/store/logs/{sub_id}")

            batch.set(purchase_ref, {
                "purchase_id": sub_id,
                "product_id": pid,
                "title": p.title,
                "quantity": qty,
                "unit_price": float(p.price),
                "total_cost": float(p.price) * qty,
                "timestamp": firestore.SERVER_TIMESTAMP,
            })
            batch.set(product_ref, {
                "product_id": pid,
                "stock": firestore.Increment(qty),
                "merchant_price": float(p.price) * 1.15,
                "platform_price": float(p.price),
                "status": "active",
                "updated_at": firestore.SERVER_TIMESTAMP,
            }, merge=True)
            batch.set(log_ref, {
                "type": "batch_purchase",
                "desc": f"批量采购 {p.title} × {qty}",
                "amount": -float(p.price) * qty,
                "timestamp": firestore.SERVER_TIMESTAMP,
            })

        await asyncio.to_thread(batch.commit)
        return PedroResponse.success(data={
            "batch_id": batch_id,
            "total_cost": total_cost,
            "count": len(items),
            "msg": "批量采购成功"
        })
