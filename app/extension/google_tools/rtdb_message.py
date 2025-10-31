"""
Firebase RTDB 消息服务 (支持未读/已读)
"""
import time
import uuid
from typing import Callable, Dict, Any

from app.extension.google_tools.rtdb import rtdb
from app.extension.redis.redis_client import rds


class RTDBMessageService:
    def __init__(self):
        self.client = rtdb  # ✅ 兼容旧写法

    # -----------------------------------------
    # ✉️ 发送消息
    # -----------------------------------------
    async def send_message(self, uid: int, text: str, sender: str = "system", extra: dict = None):
        msg_id = uuid.uuid4().hex
        now_ms = int(time.time() * 1000)

        msg = {
            "id": msg_id,
            "from": sender,
            "text": text,
            "ts": now_ms,
            **(extra or {}),
        }

        # ✅ 统一 path 构建
        path = rtdb.path("user_messages", uid, "unread", msg_id)
        rtdb.set(path, msg)

        return {"msg_id": msg_id, "ts": now_ms}

    # -----------------------------------------
    # 📥 获取未读消息
    # -----------------------------------------
    async def get_unread(self, uid: int) -> Dict[str, Any]:
        path = rtdb.path("user_messages", uid, "unread")
        return rtdb.get(path) or {}

    # -----------------------------------------
    # ✅ 标记单条消息已读
    # -----------------------------------------
    async def mark_read(self, uid: int, msg_id: str):
        redis_key = f"rtdb_msg:{uid}:{msg_id}:read"
        r = await rds.instance()

        # 幂等：已处理跳过
        if await r.get(redis_key):
            return

        unread_path = rtdb.path("user_messages", uid, "unread", msg_id)
        read_path = rtdb.path("user_messages", uid, "read", msg_id)

        msg = rtdb.get(unread_path)
        if not msg:
            return

        msg["read_at"] = int(time.time() * 1000)

        rtdb.set(read_path, msg)
        rtdb.delete(unread_path)

        await r.setex(redis_key, 7 * 24 * 60 * 60, 1)

    # -----------------------------------------
    # ✅ 标记所有已读
    # -----------------------------------------
    async def mark_all_read(self, uid: int):
        unread = await self.get_unread(uid)
        for msg_id in unread.keys():
            await self.mark_read(uid, msg_id)

    # -----------------------------------------
    # 🔔 监听新消息（实时推送，比如 WS）
    # -----------------------------------------
    def listen(self, uid: int, callback: Callable[[dict], None]):
        path = rtdb.path("user_messages", uid, "unread")

        def handler(event):
            # ✅ 只监听新增消息
            if event.data and isinstance(event.data, dict):
                callback(event.data)

        # ✅ 调用你 rtdb 的 listen
        rtdb.listen(path, handler)


# ✅ 单例实例
rtdb_msg = RTDBMessageService()
