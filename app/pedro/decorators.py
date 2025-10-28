# -*- coding: utf-8 -*-
"""
Pedro FastAPI 装饰器语法糖兼容层
支持：
✅ @login_required
✅ @group_required(['admin'])
✅ @permission_meta(...)
兼容 Flask 风格写法，但内部基于 FastAPI 依赖实现。
"""

from functools import wraps
from fastapi import Depends
from app.pedro.pedro_jwt import current_user


# ======================================================
# ✅ 登录验证装饰器
# ======================================================
def login_required(func=None):
    """
    用法：
    @login_required
    async def route(...):
        ...
    """
    def decorator(f):
        @wraps(f)
        async def wrapper(*args, user=Depends(current_user()), **kwargs):
            return await f(*args, user=user, **kwargs)
        return wrapper

    # 兼容无括号用法
    if func is None:
        return decorator
    else:
        return decorator(func)


# ======================================================
# ✅ 角色验证装饰器
# ======================================================
def group_required(roles):
    """
    用法：
    @group_required(["admin"])
    async def route(...):
        ...
    """
    def decorator(f):
        @wraps(f)
        async def wrapper(*args, user=Depends(require_roles(roles)), **kwargs):
            return await f(*args, user=user, **kwargs)
        return wrapper
    return decorator


# ======================================================
# ✅ 权限元信息（用于权限同步，可选）
# ======================================================
def permission_meta(name: str, module: str = "default", mount: bool = True):
    """
    用法：
    @permission_meta(name="查看用户", module="Admin")
    async def route(...):
        ...
    """
    def decorator(f):
        setattr(f, "permission_meta", {"name": name, "module": module, "mount": mount})
        return f
    return decorator