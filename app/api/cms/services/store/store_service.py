from firebase_admin import firestore
from app.extension.google_tools.firestore import fs_service
from app.pedro.response import PedroResponse


class AdminStoreService:

    @staticmethod
    async def list_all_purchase_records(
        status: str = None,
        keyword: str = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PedroResponse:

        # 跨全部商户的订单记录
        query = fs_service.db.collection_group("orders") \
            .order_by("created_at", direction=firestore.firestore.Query.DESCENDING)

        # 状态过滤
        if status:
            query = query.where("status", "==", status)

        # 查询 Firestore
        docs = query.stream()
        all_docs = []

        for doc in docs:
            d = doc.to_dict()

            # ⚠️ 兼容未存 merchant_id 的旧数据
            # users/{merchant_id}/store/meta/orders/{order_id}
            merchant_id = doc.reference.path.split("/")[1]
            d["merchant_id"] = merchant_id
            d["order_id"] = doc.id

            # 关键字（客户端过滤）
            if keyword:
                if keyword.lower() not in str(d).lower():
                    continue

            all_docs.append(d)

        # 分页
        total = len(all_docs)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = all_docs[start:end]

        return PedroResponse.page(
            items=page_items,
            total=total,
            page=page,
            size=page_size
        )
