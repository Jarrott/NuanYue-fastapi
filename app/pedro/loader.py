"""
# @Time    : 2025/10/27 0:19
# @Author  : Pedro
# @File    : loader.py
# @Software: PyCharm
"""
"""
PedroLoader
-----------
轻量级插件模型注册器（FastAPI 版）
✅ 自动扫描并注册所有继承自 db.Model 的类
✅ 不加载路由、不加载 Redprint、不加载服务
✅ 兼容 LinCMS 式插件结构（例如 plugin.xxx.app.__init__）
"""

from importlib import import_module
from typing import Dict, Type
from .db import Base  # 你自己的 SQLAlchemy Base 类，比如 Base = declarative_base()

class Loader:
    def __init__(self, plugin_path: dict):
        """
        plugin_path 示例:
        {
            "book": {"path": "app.plugin.book", "enable": True},
            "cms": {"path": "app.plugin.cms", "enable": False}
        }
        """
        assert isinstance(plugin_path, dict), "plugin_path 必须是 dict"
        self.plugin_path = plugin_path
        self.models: Dict[str, Type[Base]] = {}
        self.load_models()

    def load_models(self):
        """加载所有启用插件的 db.Model 子类"""
        for name, conf in self.plugin_path.items():
            if not conf.get("enable"):
                continue
            path = conf.get("path")
            if path:
                try:
                    mod = import_module(f"{path}.app.__init__")
                    self._register_models_from_module(mod, plugin_name=name)
                except ModuleNotFoundError:
                    print(f"⚠️ 模块未找到: {path}.app.__init__")
                except Exception as e:
                    print(f"❌ 加载插件 {name} 失败: {e}")

    def _register_models_from_module(self, mod, plugin_name: str):
        """遍历模块属性，注册所有继承 Base 的类"""
        count = 0
        for key, attr in mod.__dict__.items():
            if isinstance(attr, type) and issubclass(attr, Base) and attr is not Base:
                self.models[f"{plugin_name}.{key}"] = attr
                count += 1
        print(f"✅ 已注册 {count} 个模型来自插件 [{plugin_name}]")

    def get_model(self, name: str):
        """获取模型类（支持 plugin.ModelName 形式）"""
        return self.models.get(name)

    def summary(self):
        print("\n📦 已加载模型:")
        for key in self.models:
            print(f"  - {key}")
        print("========================================\n")