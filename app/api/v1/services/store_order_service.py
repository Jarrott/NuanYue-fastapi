"""
💰 商户补货服务（含钱包扣款 + Firestore + RTDB 同步）
"""

import uuid
import json
from firebase_admin.firestore import firestore
from starlette.responses import JSONResponse
from app.extension.google_tools.firestore import fs_service as fs
from app.extension.google_tools.fs_transaction import SERVER_TIMESTAMP
from app.extension.google_tools.firebase_admin_service import rtdb
from app.api.cms.services.wallet.wallet_secure_service import WalletSecureService
from app.pedro.response import PedroResponse
from app.pedro.db import async_session_factory
from app.api.v1.model.shop_product import ShopProduct
from sqlalchemy import select


class RestockService:

    # ==============================================================
    # 🔧 通用解析：兼容 dict / JSONResponse / PedroResponse
    # ==============================================================
    @staticmethod
    def _unwrap_response(result):
        """自动识别 PedroResponse / JSONResponse / dict 类型"""
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

    # ==============================================================
    # 🛒 查询商户缺货订单
    # ==============================================================
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

    # ==============================================================
    # 💰 一键补货（含扣款 + 多源同步）
    # ==============================================================
    @staticmethod
    async def restock_all(uid: str):
        # 1️⃣ 获取缺货订单
        orders = await RestockService.list_need_purchase_orders(uid)
        if not orders:
            return PedroResponse.fail(msg="当前没有缺货订单")

        # 2️⃣ 聚合商品并计算总价
        product_ids = list({o["product_id"] for o in orders})
        async with async_session_factory() as session:
            result = await session.execute(
                select(ShopProduct).where(ShopProduct.id.in_(product_ids))
            )
            products = {str(p.id): p for p in result.scalars().all()}

        total_amount = 0
        purchase_items = []

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

        # 3️⃣ 执行钱包扣款（同步 Firestore + RTDB + Ledger）
        reference = f"restock_{uuid.uuid4().hex[:8]}"
        result = await WalletSecureService.debit_wallet(
            uid=uid,
            amount=total_amount,
            reference=reference,
            source="restock",
            desc=f"补货扣款 {len(purchase_items)} 件商品，总计 {total_amount:.2f}",
            operator="system"
        )

        # ✅ 兼容 JSONResponse / dict
        result_data = RestockService._unwrap_response(result)

        # 兼容两种结构 {"data": {...}} 或 {...}
        data_block = result_data.get("data", result_data)
        status = data_block.get("status")
        balance = data_block.get("balance", 0)

        if status == "insufficient":
            return PedroResponse.fail(msg="余额不足，请先充值")
        if status == "duplicate":
            return PedroResponse.fail(msg="重复扣款")

        # 4️⃣ 创建 Firestore 采购批次
        batch_id = uuid.uuid4().hex
        batch_path = f"users/{uid}/store/meta/purchases/{batch_id}"
        batch_doc = {
            "batch_id": batch_id,
            "items": purchase_items,
            "total_amount": total_amount,
            "reference": reference,
            "status": "purchased",
            "created_at": SERVER_TIMESTAMP,
            "updated_at": SERVER_TIMESTAMP
        }
        fs.db.document(batch_path).set(batch_doc)

        # 5️⃣ 更新所有 need_purchase 订单状态 → pending
        for order in orders:
            order_path = f"users/{uid}/store/meta/orders/{order['order_id']}"
            fs.db.document(order_path).update({
                "status": "pending",
                "updated_at": SERVER_TIMESTAMP,
                "purchase_batch": batch_id
            })

        # 6️⃣ RTDB 同步商户钱包
        ref = rtdb.reference(f"user_{uid}")
        ref.update({
            "last_transaction": reference,
            "balance": float(balance)
        })

        return PedroResponse.success(
            msg=f"成功补货 {len(purchase_items)} 件商品，总金额 {total_amount:.2f}",
            # data={
            #     "batch_id": batch_id,
            #     "total_amount": total_amount,
            #     "items": purchase_items,
            #     "balance": balance
            # }
        )
