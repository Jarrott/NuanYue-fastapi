"""
# @Time    : 2025/11/14 22:09
# @Author  : Pedro
# @File    : flash_sale_service.py
# @Software: PyCharm
"""
from datetime import timezone

from google.cloud.firestore_v1 import FieldFilter

from app.extension.google_tools.firestore import fs_service
from app.extension.google_tools.fs_transaction import SERVER_TIMESTAMP
from app.pedro.response import PedroResponse


async def create_home_flash_datetime_sale(body):
    db = fs_service.db  # 为可读性

    # 1️⃣ 查询是否已经存在未结束的首页秒杀活动
    query = (
        db.collection("flash_sale")
        .where(filter=FieldFilter("type", "==", "home_flash_sale"))
        .where(filter=FieldFilter("status", "in", ["online", "active"]))  # ✅ 关键
        .limit(1)
    )


    docs = query.get()  # 🔥 最新 API


    if docs:  # (等同于 len(docs) > 0)
        return False

    # 2️⃣ 创建新活动
    doc_ref = db.collection("flash_sale").document()

    data = {
        "id": doc_ref.id,
        "type": "home_flash_sale",
        "title": body.title,
        "start_time": body.start_time.replace(tzinfo=timezone.utc),
        "end_time": body.end_time.replace(tzinfo=timezone.utc),
        "status": "online",
        "created_at": SERVER_TIMESTAMP,
    }

    doc_ref.set(data)

    # 3️⃣ 同步 RTDB + WS（若开启）
    try:
        from app.api.cms.services.flash_sync_runtime import FlashSyncRuntime
        await FlashSyncRuntime.on_start(doc_ref.id,end_time=body.end_time.replace(tzinfo=timezone.utc))
    except Exception:
        pass  # 即便推送失败，也不影响写库

    return True
