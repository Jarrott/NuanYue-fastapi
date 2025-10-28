"""
# @Time    : 2025/10/28 21:54
# @Author  : Pedro
# @File    : base.py
# @Software: PyCharm
"""
import asyncio
import json
from typing import Dict, Any, List, Callable

class EventBus:
    """通用异步事件总线"""
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}
        self.adapters = []

    def register_adapter(self, adapter):
        """注册适配器（Redis/MQ/WS等）"""
        self.adapters.append(adapter)

    def on(self, event_name: str):
        """注册本地事件监听器"""
        def wrapper(func):
            self.subscribers.setdefault(event_name, []).append(func)
            return func
        return wrapper

    async def publish(self, event_name: str, data: Dict[str, Any]):
        """发布事件（多通道分发）"""
        payload = {"event": event_name, "data": data}
        # ✅ 广播到所有适配器
        for adapter in self.adapters:
            try:
                await adapter.publish(event_name, payload)
            except Exception as e:
                print(f"⚠️ Adapter {adapter.__class__.__name__} error: {e}")

        # ✅ 调用本地监听器
        for fn in self.subscribers.get(event_name, []):
            try:
                await fn(data)
            except Exception as e:
                print(f"⚠️ Local handler error: {e}")

# ✅ 单例
eventbus = EventBus()
