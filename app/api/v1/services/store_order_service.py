# @Time    : 2025/11/10 07:30
# @Author  : Pedro
# @File    : restock_service.py
# @Software: PyCharm
"""
💰 商户补货服务（含钱包扣款 + Firestore + RTDB + SQL 同步）
"""

import uuid
import json
from firebase_admin.firestore import firestore
from starlette.responses import JSONResponse
from sqlalchemy import select

from app.extension.google_tools.firestore import fs_service as fs
from app.extension.google_tools.fs_transaction import SERVER_TIMESTAMP
from app.api.cms.services.wallet.wallet_secure_service import WalletSecureService
from app.api.cms.services.wallet.base_wallet_sync import BaseWalletSyncService  # ✅ 正确路径
from app.pedro.response import PedroResponse
from app.pedro.db import async_session_factory
from app.api.v1.model.shop_product import ShopProduct


class RestockService(BaseWalletSyncService):
    """统一补货服务"""

    # ------------------------------------------------------
    # 🔧 通用解析：兼容 dict / JSONResponse / PedroResponse
    # ------------------------------------------------------
    @staticmethod
    def _unwrap_response(result):
        if isinstance(result, JSONResponse):
            try:
                return json.loads(result.body.decode())
            except Exception:
                return {}
        if hasattr(result, "model_dump"):  # pydantic model
            return result.model_dump()
        if isinstance(result, dict):
            return result
        return {}

    # ------------------------------------------------------
    # 🛒 查询商户缺货订单
    # ------------------------------------------------------
    @staticmethod
    async def list_need_purchase_orders(uid: str, limit: int = 50):
        path = f"users/{uid}/store/meta/orders"
        query = (
            fs.db.collection(path)
            .where("status", "==", "need_purchase")
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        docs = query.stream()
        return [doc.to_dict() for doc in docs if doc.to_dict()]

    # ------------------------------------------------------
    # 💰 一键补货
    # ------------------------------------------------------
    @classmethod
    async def restock_all(cls, uid: str):
        orders = await cls.list_need_purchase_orders(uid)
        if not orders:
            return PedroResponse.fail(msg="当前没有缺货订单")

        # 🔍 查询商品详情
        product_ids = list({o["product_id"] for o in orders})
        async with async_session_factory() as session:
            result = await session.execute(select(ShopProduct).where(ShopProduct.id.in_(product_ids)))
            products = {str(p.id): p for p in result.scalars().all()}

        total_amount, purchase_items = 0, []
        for order in orders:
            pid = str(order["product_id"])
            qty = int(order.get("qty", 1))
            product = products.get(pid)
            if not product:
                continue
            subtotal = float(product.price) * qty
            total_amount += subtotal
            purchase_items.append({
                "product_id": pid,
                "quantity": qty,
                "subtotal": subtotal,
                "product_name": product.title
            })

        if not purchase_items:
            return PedroResponse.fail(msg="未找到可采购商品")

        # 💳 扣款
        reference = f"restock_{uuid.uuid4().hex[:8]}"
        result = await WalletSecureService.debit_wallet(
            uid=uid,
            amount=total_amount,
            reference=reference,
            l_type="restock",
            desc=f"补货扣款 {len(purchase_items)} 件商品，总计 {total_amount:.2f}",
            operator_id="system"
        )

        result_data = cls._unwrap_response(result)
        data_block = result_data.get("data", result_data)
        status = data_block.get("status")
        balance = data_block.get("balance_after") or data_block.get("balance") or 0

        if status == "insufficient":
            return PedroResponse.fail(msg="余额不足，请先充值")
        if status == "duplicate":
            return PedroResponse.fail(msg="重复扣款")

        # 🔖 Firestore 批次
        batch_id = uuid.uuid4().hex
        fs.db.document(f"users/{uid}/store/meta/purchases/{batch_id}").set({
            "batch_id": batch_id,
            "items": purchase_items,
            "total_amount": total_amount,
            "reference": reference,
            "status": "purchased",
            "created_at": SERVER_TIMESTAMP,
            "updated_at": SERVER_TIMESTAMP
        })

        # 🧾 更新订单状态
        for order in orders:
            fs.db.document(f"users/{uid}/store/meta/orders/{order['order_id']}").update({
                "status": "pending",
                "updated_at": SERVER_TIMESTAMP,
                "purchase_batch": batch_id
            })

        # ✅ 调用抽象同步逻辑（统一到 PostgreSQL + Redis + RTDB）
        await cls.sync_all(uid, float(balance))

        return PedroResponse.success(
            msg=f"成功补货 {len(purchase_items)} 件商品，总金额 {total_amount:.2f}"
        )

    # ------------------------------------------------------
    # 💰 单独补货
    # ------------------------------------------------------
    @classmethod
    async def restock_single(cls, uid: str, order_id: str):
        order_path = f"users/{uid}/store/meta/orders/{order_id}"
        order_doc = await fs.get(order_path)
        if not order_doc:
            return PedroResponse.fail(msg=f"订单不存在: {order_id}")

        if order_doc.get("status") != "need_purchase":
            return PedroResponse.fail(msg=f"订单状态非缺货状态: {order_doc.get('status')}")

        pid = int(order_doc["product_id"])
        qty = int(order_doc.get("qty", 1))

        async with async_session_factory() as session:
            result = await session.execute(select(ShopProduct).where(ShopProduct.id == pid))
            product = result.scalar_one_or_none()
            if not product:
                return PedroResponse.fail(msg=f"商品不存在: {pid}")

            subtotal = float(product.price) * qty

        reference = f"restock_single_{order_id}"
        result = await WalletSecureService.debit_wallet(
            uid=uid,
            amount=subtotal,
            reference=reference,
            source="restock_single",
            desc=f"单独补货 {product.title} × {qty}",
            operator="system"
        )

        result_data = cls._unwrap_response(result)
        data_block = result_data.get("data", result_data)
        status = data_block.get("status")
        balance = data_block.get("balance_after") or data_block.get("balance") or 0

        if status == "insufficient":
            return PedroResponse.fail(msg="余额不足，无法补货")

        batch_id = f"RESTOCK-{uuid.uuid4().hex[:10]}"
        fs.db.document(f"users/{uid}/store/meta/purchases/{batch_id}").set({
            "batch_id": batch_id,
            "items": [{
                "product_id": pid,
                "product_name": product.title,
                "quantity": qty,
                "subtotal": subtotal,
            }],
            "total_amount": subtotal,
            "reference": reference,
            "status": "purchased",
            "created_at": firestore.SERVER_TIMESTAMP,
        })

        fs.db.document(order_path).update({
            "status": "pending",
            "purchase_batch": batch_id,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })

        # ✅ 调用抽象同步逻辑
        await cls.sync_all(uid, float(balance))

        return PedroResponse.success(
            msg=f"✅ 成功补货订单 {order_id}，金额 {subtotal:.2f} USD",
            data={
                "order_id": order_id,
                "batch_id": batch_id,
                "amount": subtotal,
                "balance": balance
            }
        )
