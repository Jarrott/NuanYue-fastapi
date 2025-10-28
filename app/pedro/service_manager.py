"""
Pedro-Core | 通用服务注册与动态加载模块
------------------------------------
✅ 自动扫描 app/extension 下的所有服务类
✅ 每个服务继承 BaseService 即可自动注册
✅ 支持 FastAPI 生命周期自动启动与关闭
"""

import asyncio
import inspect
import pkgutil
import importlib
from typing import Dict, Type, Any


class BaseService:
    """所有服务模块的基类"""
    name: str = "base"

    async def init(self):
        """初始化逻辑"""
        raise NotImplementedError

    async def close(self):
        """关闭逻辑"""
        pass


class ServiceManager:
    """统一的服务管理器"""
    _services: Dict[str, BaseService] = {}

    # ======================================================
    # 初始化加载
    # ======================================================
    @classmethod
    async def init_all(cls):
        """自动发现并加载所有 BaseService 子类"""
        print("🔍 ServiceManager: 正在扫描 app/extension 下的服务模块...")
        for finder, name, ispkg in pkgutil.iter_modules(["app/extension"]):
            try:
                module = importlib.import_module(f"app.extension.{name}")
                for attr_name in dir(module):
                    obj = getattr(module, attr_name)
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, BaseService)
                        and obj is not BaseService
                    ):
                        instance = obj()
                        await instance.init()
                        cls._services[obj.name] = instance
                        print(f"✅ 已加载服务: {obj.name}")
            except Exception as e:
                print(f"⚠️ 加载服务模块失败: {name}, 原因: {e}")

    # ======================================================
    # 获取服务
    # ======================================================
    @classmethod
    def get(cls, name: str) -> BaseService:
        service = cls._services.get(name)
        if not service:
            raise KeyError(f"❌ 服务 '{name}' 未注册或初始化失败")
        return service

    # ======================================================
    # 关闭所有服务
    # ======================================================
    @classmethod
    async def close_all(cls):
        """关闭所有服务"""
        for name, service in cls._services.items():
            try:
                await service.close()
                print(f"🛑 已关闭服务: {name}")
            except Exception as e:
                print(f"⚠️ 关闭服务 {name} 失败: {e}")


# 单例实例
service = ServiceManager()