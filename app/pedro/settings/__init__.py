"""
# @Time    : 2025/10/28 1:38
# @Author  : Pedro
# @File    : __init__.py.py
# @Software: PyCharm
"""
# app/core/config/__init__.py
import threading
from functools import lru_cache
from typing import Optional
from fastapi import FastAPI

from .loader import load_config_file
from .parser import deep_merge_dict, normalize_keys
from .models import SettingsModel
import os

# ======================================================
# 🧠 全局单例 + 线程安全锁
# ======================================================
_settings_instance: Optional[SettingsModel] = None
_settings_lock = threading.Lock()


# ======================================================
# 🧩 Settings 主类（负责合并 + 动态注入）
# ======================================================
class Settings(SettingsModel):
    def __init__(self):
        super().__init__()
        env = os.getenv("APP_ENV", "development")
        data = normalize_keys(load_config_file(env))

        for key, val in data.items():
            if hasattr(self, key.lower()):
                current = getattr(self, key.lower())
                if isinstance(val, dict):
                    merged = deep_merge_dict(current.dict(), val)
                    setattr(self, key.lower(), type(current)(**merged))
            else:
                setattr(self, key.lower(), val)
                setattr(self, key.upper(), val)


# ======================================================
# 🔧 获取配置实例（懒加载 + 缓存）
# ======================================================
@lru_cache
def get_settings() -> Settings:
    """获取配置实例（带缓存）"""
    global _settings_instance
    if not _settings_instance:
        with _settings_lock:
            if not _settings_instance:
                _settings_instance = Settings()
    return _settings_instance


# ======================================================
# 🚀 注册到 FastAPI 应用
# ======================================================
def init_settings(app: Optional[FastAPI] = None) -> Settings:
    """初始化 Settings 并注册到 FastAPI"""
    settings = get_settings()
    if app:
        app.state.settings = settings
        print(f"✅ 配置系统已注册到 FastAPI: {settings.app.name} ({settings.app.env})")
    return settings
