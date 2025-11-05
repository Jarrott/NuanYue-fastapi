# -*- coding:utf-8 -*-
"""
FastAPI 版本 LinCMS 工具集
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
保留原 LinCMS 功能：
✅ 动态加载 Python 模块
✅ 权限元信息注册
✅ 驼峰转下划线命名
✅ 随机字符串生成
✅ 时间戳生成
"""

import errno
import importlib.util
import os
import random
import re
import time
import types
from datetime import timedelta
from importlib import import_module
from collections import namedtuple
from typing import Any, Callable, Dict, Union


# ======================================================
# 基础工具函数
# ======================================================
def get_timestamp(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    获取当前时间戳并按格式返回
    """
    return time.strftime(fmt, time.localtime())


def get_pwd() -> str:
    """
    获取当前工作目录的绝对路径
    """
    return os.path.abspath(os.getcwd())


def camel2line(camel: str) -> str:
    """
    驼峰命名 -> 下划线命名
    例如：UserGroup -> user_group
    """
    p = re.compile(r"([a-z0-9])([A-Z])")
    return re.sub(p, r"\1_\2", camel).lower()


def get_random_str(length: int = 8) -> str:
    """
    生成指定长度的随机字符串
    """
    chars = "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return "".join(random.choice(chars) for _ in range(length))


# ======================================================
# Python 文件与模块操作
# ======================================================
def get_pyfile(path: str, module_name: str, silent: bool = False) -> Union[Dict[str, Any], bool]:
    """
    获取 Python 文件内的所有属性（类似 execfile）
    """
    mod = types.ModuleType(module_name)
    mod.__file__ = path

    try:
        with open(path, mode="rb") as f:
            code = compile(f.read(), path, "exec")
            exec(code, mod.__dict__)
    except IOError as e:
        if silent and e.errno in (errno.ENOENT, errno.EISDIR, errno.ENOTDIR):
            return False
        raise IOError(f"无法加载配置文件: {e}")
    return mod.__dict__


def load_object(path: str) -> Any:
    """
    动态加载模块中的对象。
    例如：'app.models.user.User' -> 返回 User 类
    """
    try:
        module_path, obj_name = path.rsplit(".", 1)
    except ValueError:
        raise ValueError(f"加载对象 '{path}' 失败：路径必须包含模块名和对象名")

    module = import_module(module_path)
    if not hasattr(module, obj_name):
        raise NameError(f"模块 '{module_path}' 中未定义 '{obj_name}'")

    return getattr(module, obj_name)


def import_module_abs(name: str, path: str) -> None:
    """
    使用绝对路径加载模块。
    示例：
        import_module_abs("custom_config", "/path/to/config.py")
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)


# ======================================================
# 权限信息装饰器 (核心功能)
# ======================================================

Meta = namedtuple("Meta", ["name", "module", "mount"])
permission_meta_infos: Dict[str, Meta] = {}


def permission_meta(name: str, module: str = "common", mount: bool = True):
    """
    权限信息装饰器，用于标记路由权限元数据。
    ⚙️ FastAPI 版本支持：
      - 在路由函数上添加权限描述信息
      - 自动记录 name/module/mount 信息
    示例：
        @permission_meta("查看用户列表", module="用户管理")
        async def list_users():
            ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        key = f"{func.__module__}.{func.__name__}"
        if key in permission_meta_infos:
            existing = permission_meta_infos[key]
            if existing.module == module:
                raise RuntimeError(f"函数 '{func.__name__}' 在模块 '{module}' 中已注册权限")
        permission_meta_infos[key] = Meta(name=name, module=module, mount=mount)
        return func

    return decorator


# ======================================================
# 其他实用函数
# ======================================================
def ensure_dir(path: str) -> None:
    """
    若目录不存在则自动创建
    """
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def is_python_module(path: str) -> bool:
    """
    判断是否为 Python 文件或模块
    """
    return os.path.isfile(path) and path.endswith(".py")


def list_py_files(directory: str) -> list[str]:
    """
    列出目录下的所有 Python 文件（递归）
    """
    py_files = []
    for root, _, files in os.walk(directory):
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
    return py_files


def normalize_lang(lang: str | None) -> str:
    if not lang:
        return "en"

    # en_US -> en, zh_CN -> zh ...
    primary = lang.split("_")[0].lower()

    # 我们支持的语言列表
    # supported = {"en", "zh", "jp", "kr"}
    return primary

def parse_duration(value: str) -> timedelta:
    """支持 30m / 1h / 7d / 3600s / 1800 格式"""
    value = str(value).strip().lower()

    units = {
        "s": "seconds",
        "m": "minutes",
        "h": "hours",
        "d": "days",
    }

    # 仅数字 = 默认秒
    if value.isdigit():
        return timedelta(seconds=int(value))

    unit = value[-1]
    amount = value[:-1]

    if unit in units and amount.isdigit():
        return timedelta(**{units[unit]: int(amount)})

    raise ValueError(f"Invalid duration format: {value}. e.g. 30m / 1h / 7d / 3600")
