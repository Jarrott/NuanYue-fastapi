from fastapi import APIRouter, WebSocket

from starlette.websockets import WebSocketDisconnect

from app.extension.websocket.tasks.market_handler import market_handler
from app.extension.websocket.utils.ws_entry import ws_entry

rp = APIRouter(prefix="/ws", tags=["WebSocket"])


@rp.websocket("/")
async def ws_init(ws: WebSocket):
    # 自动鉴权 / connect / 订阅所有频道 / 心跳 / 踢超时 / 续期提醒 全都内置
    await ws_entry(ws, market_handler, auto_subscribe_all=True)

@rp.websocket("/ping")
async def ws_ping(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            t0 = await ws.receive_text()
            await ws.send_text(t0)
    except WebSocketDisconnect:
        print("⚠️ WebSocket client disconnected")
    except Exception as e:
        print(f"❌ WebSocket error: {e}")