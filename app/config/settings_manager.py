"""
Pedro-Core Settings Manager (Safe Lazy Import)
--------------------------------
✅ 支持全局单例访问
✅ 自动注册到 FastAPI
✅ 彻底避免 config ↔ pedro 循环导入
"""

from functools import lru_cache
from typing import Optional
from fastapi import FastAPI

# 全局变量存储当前 Settings 实例
_settings_instance: Optional["Settings"] = None


def init_settings(app: Optional[FastAPI] = None) -> "Settings":
    """
    初始化并注册 settings。
    - 若已存在实例，则复用；
    - 若传入 app，则注册到 app.state；
    """
    global _settings_instance
    if _settings_instance is None:
        # ✅ 延迟导入，防止循环
        from app.pedro.config import get_settings, Settings
        _settings_instance = get_settings()
        print(f"✅ Settings initialized: ENV={_settings_instance.ENV}")
    if app is not None:
        app.state.settings = _settings_instance
    return _settings_instance


@lru_cache()
def get_current_settings() -> "Settings":
    """
    从任意模块安全地获取当前 settings 实例。
    如果尚未初始化，会自动调用 get_settings()。
    """
    global _settings_instance
    if _settings_instance is None:
        # ✅ 延迟导入（与上面一样）
        from app.pedro.config import get_settings, Settings
        _settings_instance = get_settings()
    return _settings_instance
