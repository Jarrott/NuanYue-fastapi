from datetime import datetime
from google.cloud.firestore_v1 import Increment
from app.extension.redis.redis_client import rds
from app.extension.google_tools.firebase_admin_service import fs


class StoreVisitService:

    @staticmethod
    async def record_visit(uid: str | None, store_id: str):
        db = fs
        now = datetime.now()
        today_key = now.strftime("%Y-%m-%d")

        # Redis unique 去重
        r = await rds.instance()
        visit_key = f"visit:store:{store_id}:{today_key}"

        is_unique = False
        if uid:
            if await r.sadd(visit_key, uid) == 1:
                is_unique = True

        await r.expire(visit_key, 60 * 60 * 24 * 2)

        # Firestore stats ref
        ref = (db.collection("users").document(store_id)
               .collection("store").document("meta")
               .collection("stats").document("overview"))

        # 🔍 判断今天是否需要重置 today 计数
        snap = ref.get()
        data = snap.to_dict() or {}
        last_update_day = data.get("last_visit_day")

        if last_update_day != today_key:
            ref.update({
                "visits.today": 0,
                "last_visit_day": today_key
            })

        # 写入更新
        update_data = {
            "visits.today": Increment(1),
            "visits.total": Increment(1),
            "update_time": now,
            "last_visit_day": today_key
        }

        if is_unique:
            update_data["visits.unique"] = Increment(1)

        ref.update(update_data)

        return True
