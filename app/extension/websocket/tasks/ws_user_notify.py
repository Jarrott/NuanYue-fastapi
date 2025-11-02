"""
# @Time    : 2025/11/2 22:38
# @Author  : Pedro
# @File    : ws_user_notify.py
# @Software: PyCharm
"""
from app.extension.websocket.wss import websocket_manager


async def notify_user(uid: int, event: dict, broadcast: bool = False):
    """
    WebSocket 用户通知
    broadcast=True  -> 广播给所有在线用户
    broadcast=False -> 私聊，仅 user:{id}
    """

    payload = {
        "type": "user",  # ✅ 前端识别字段
        "uid": uid,
        **event
    }

    if broadcast:
        # ✅ 全平台广播
        await websocket_manager.broadcast_all("broadcast", payload)
    else:
        # ✅ 私人频道
        channel = f"user:{uid}"
        await websocket_manager.broadcast(channel, payload)


async def notify_broadcast(event: dict):
    """
    ✅ 推送系统广播（全局消息）
    """
    payload = {
        "type": "broadcast",
        "broadcast": True,
        **event
    }
    await websocket_manager.broadcast_all(payload)
