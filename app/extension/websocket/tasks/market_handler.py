import json
from fastapi import WebSocket
from app.extension.websocket.wss import websocket_manager


async def market_handler(ws: WebSocket, uid: int):
    """
    业务层仅处理“非控制类”消息（控制类已在 ws_entry 处理：ping/pong、refresh）
    下面是示例：订阅/退订/回显
    """
    data = await ws.receive_text()
    try:
        msg = json.loads(data)
    except Exception:
        msg = {"type": "text", "data": data}

    act = msg.get("action")
    if act == "subscribe":
        ch = msg.get("channel")
        await websocket_manager.subscribe(ws, ch)
        await ws.send_json({"type": "system", "msg": f"subscribed:{ch}"})
    elif act == "unsubscribe":
        ch = msg.get("channel")
        await websocket_manager.unsubscribe(ws, ch)
        await ws.send_json({"type": "system", "msg": f"unsubscribed:{ch}"})
    else:
        await ws.send_json({"type": "echo", "data": msg})