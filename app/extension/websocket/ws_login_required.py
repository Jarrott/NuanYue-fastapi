from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect
from urllib.parse import parse_qs
from app.pedro.model import User
from app.pedro.pedro_jwt import jwt_service
from app.extension.websocket.wss import websocket_manager


class WebSocketConnection:
    @staticmethod
    async def authenticate(ws: WebSocket):
        """统一鉴权"""
        query = parse_qs(ws.url.query)
        token = query.get("token", [None])[0]

        if not token:
            await ws.close(code=4001, reason="Missing token")
            return None

        try:
            payload = jwt_service.verify(token)
            uid = payload.get("uid")
        except Exception:
            await ws.close(code=4002, reason="Invalid token")
            return None

        user = await User.get(id=uid)
        if not user:
            await ws.close(code=4003, reason="User not found")
            return None

        return uid, user

    @staticmethod
    async def entry(ws: WebSocket, business_handler):
        """统一接入入口 + 分发业务逻辑"""
        await ws.accept()

        auth = await WebSocketConnection.authenticate(ws)
        if not auth:
            return

        uid, user = auth
        await websocket_manager.connect(ws, uid)

        print(f"🟢 WebSocket 用户 {uid} 已连接")

        try:
            # ✅ 走具体业务处理
            await business_handler(ws, uid, user)

        except WebSocketDisconnect:
            print(f"⚠️ WebSocket 用户 {uid} 断开")
        except Exception as e:
            print(f"❌ WebSocket error {uid}: {e}")
        finally:
            await websocket_manager.disconnect(ws)
            print(f"🔴 WebSocket 用户 {uid} 离线")
