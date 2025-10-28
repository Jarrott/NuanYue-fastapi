from fastapi import APIRouter, WebSocket
from urllib.parse import parse_qs
from app.extension.websocket.wss import websocket_manager
import json

rp = APIRouter(prefix="/ws", tags=["WebSocket"])

@rp.websocket("/market")
async def market_ws(ws: WebSocket):
    query = parse_qs(ws.url.query)
    uid = query.get("uid", ["anonymous"])[0]

    await ws.accept()
    await websocket_manager.connect(ws, uid)
    print(f"🟢 用户 {uid} 已连接")

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            # ✅ 客户端订阅频道
            if msg.get("action") == "subscribe":
                channel = msg.get("channel")
                await websocket_manager.subscribe(ws, channel)
                await ws.send_json({"msg": f"✅ 已订阅 {channel}"})

            # ✅ 客户端取消订阅
            elif msg.get("action") == "unsubscribe":
                channel = msg.get("channel")
                await websocket_manager.unsubscribe(ws, channel)
                await ws.send_json({"msg": f"🚫 已取消订阅 {channel}"})

            # ✅ 测试回显
            else:
                print(f"📩 [{uid}] says:", msg)
                await ws.send_json({"echo": msg})

    except Exception as e:
        print(f"⚠️ [{uid}] 异常断开: {e}")
    finally:
        await websocket_manager.disconnect(ws)
        print(f"🔴 [{uid}] 已断开连接")
