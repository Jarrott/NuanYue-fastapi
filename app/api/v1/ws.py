from fastapi import APIRouter, WebSocket, Query
from starlette.websockets import WebSocketDisconnect
from app.extension.websocket.wss import websocket_manager
import json
import asyncio

rp = APIRouter(prefix="/ws", tags=["WebSocket服务"])

@rp.websocket("/market")
async def market_ws(ws: WebSocket, uid: str = Query(...)):
    """
    WebSocket 实时行情通道
    uid: 用户唯一标识（可用token或随机UUID）
    """
    await websocket_manager.connect(ws, uid)

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            action = msg.get("action")
            channel = msg.get("channel")

            if action == "subscribe":
                await websocket_manager.subscribe(ws, channel)
            elif action == "unsubscribe":
                await websocket_manager.unsubscribe(ws, channel)
            elif action == "pong":
                continue
            else:
                await ws.send_json({"error": "invalid_action"})
    except WebSocketDisconnect:
        await websocket_manager.disconnect(ws)
