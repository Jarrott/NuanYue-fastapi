import json
from typing import Dict, Any, List, Callable

class EventBus:
    """统一事件总线"""
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}
        self.adapters = []

    def register_adapter(self, adapter):
        self.adapters.append(adapter)

    def on(self, event_name: str):
        def wrapper(func):
            self.subscribers.setdefault(event_name, []).append(func)
            return func
        return wrapper

    async def publish(self, event_name: str, data: Dict[str, Any]):
        payload = {"event": event_name, "data": data}
        # 统一广播
        for adapter in self.adapters:
            try:
                await adapter.publish(event_name, payload)
            except Exception as e:
                print(f"⚠️ Adapter {adapter.__class__.__name__} 出错: {e}")

        # 本地触发
        for fn in self.subscribers.get(event_name, []):
            try:
                await fn(data)
            except Exception as e:
                print(f"⚠️ Local handler {fn.__name__} 出错: {e}")

eventbus = EventBus()
