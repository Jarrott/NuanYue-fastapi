# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/13 23:59
# @Author  : Pedro
# @File    : id_helper.py
# @Software: PyCharm
"""
from typing import Any

class IDHelper:
    """
    🧩 Pedro-Core 全局 ID 安全工具
    --------------------------------------------------------
    ✅ 支持 int / bigint / str 三种形式的 ID
    ✅ 优先使用 uuid（分布式雪花ID）
    ✅ 统一输出为 str，兼容 Firestore / Redis / JSON
    ✅ 自动回退到自增 id（PostgreSQL ID）
    """

    @staticmethod
    def normalize(value: Any) -> int:
        """将输入转成 int"""
        if value is None:
            raise ValueError("❌ ID 不能为空")
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        raise ValueError(f"无法识别的 ID 格式: {value}")

    @staticmethod
    def is_big_uuid(value: int) -> bool:
        """判断是否为 Snowflake UUID（> 1e12 通常为 64bit）"""
        try:
            return int(value) > 10**12
        except Exception:
            return False

    @staticmethod
    def get_uid(user: Any) -> str:
        """
        ✅ 安全获取用户唯一标识：
        优先 user.uuid → 再取 user.id → 最终转为 str
        """
        if not user:
            raise ValueError("user 对象为空")

        uid = getattr(user, "uuid", None) or getattr(user, "id", None)
        if uid is None:
            raise ValueError(f"无法从对象中提取uuid/id: {user}")

        return str(uid)

    @staticmethod
    def safe_uid(uid: Any) -> str:
        """
        ✅ 通用场景：传入 uid / user / token claim 都能安全提取字符串形式
        """
        if hasattr(uid, "uuid") or hasattr(uid, "id"):
            return IDHelper.get_uid(uid)
        if isinstance(uid, (int, float)):
            return str(int(uid))
        if isinstance(uid, str):
            return uid.strip()
        raise ValueError(f"无法解析 uid: {uid}")

    @staticmethod
    def get_firestore_path(base_path: str, user: Any) -> str:
        """
        ✅ 构造 Firestore 路径
        eg:  get_firestore_path("users/{uid}/store/profile", user)
        """
        uid = IDHelper.get_uid(user)
        return base_path.replace("{uid}", str(uid))

