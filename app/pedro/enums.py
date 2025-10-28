# -*- coding:utf-8 -*-
"""
FastAPI 版本 LinCMS 枚举定义
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
提供系统通用枚举类型：
✅ 用户分组等级
✅ 可扩展 Enum 基类
"""

from enum import Enum


class GroupLevelEnum(int, Enum):
    """
    用户组等级枚举
    用于区分系统权限层级：
      - ROOT：超级管理员
      - GUEST：访客（只读）
      - USER：普通注册用户
    """

    ROOT = 1
    GUEST = 2
    USER = 3

    def label(self) -> str:
        """返回中文描述"""
        labels = {
            GroupLevelEnum.ROOT: "超级管理员",
            GroupLevelEnum.GUEST: "访客用户",
            GroupLevelEnum.USER: "普通用户",
        }
        return labels.get(self, "未知等级")

    @classmethod
    def from_name(cls, name: str) -> "GroupLevelEnum":
        """支持通过字符串名称获取枚举"""
        name = name.strip().upper()
        if name in cls.__members__:
            return cls[name]
        raise ValueError(f"无效的用户等级名称: {name}")