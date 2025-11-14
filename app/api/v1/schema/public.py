"""
# @Time    : 2025/10/5 9:59
# @Author  : Pedro
# @File    : user.py
# @Software: PyCharm
"""
import re
from datetime import datetime, timezone
from typing import List, Optional, Any, Dict, Self, ClassVar
from pydantic import Field, validator, EmailStr, field_serializer, field_validator, computed_field
from user_agents import parse as ua_parse
from fastapi import Query
from app.api.cms.schema import GroupIdListSchema, EmailSchema
from app.pedro.exception import BaseModel, ParameterError


class BaseSchema(BaseModel):
    """通用基础Schema：支持 ORM / dict 智能识别 + 时间格式化"""

    create_time: datetime | None = None
    update_time: datetime | None = None

    # ✅ v2 新写法：允许从 ORM 属性解析
    model_config = {
        "from_attributes": True
    }

    # --------------------------------------------------
    # 自动识别 ORM / dict 的智能加载方法
    # --------------------------------------------------
    @classmethod
    def smart_load(cls, data: Any):
        if data is None:
            return None

        # ✅ ORM 对象
        if hasattr(data, "__dict__") or hasattr(data, "__table__"):

            # ✅ 检查 cls 是否自定义了 from_orm
            custom_from_orm = cls.__dict__.get("from_orm")
            base_from_orm = BaseModel.__dict__.get("from_orm")

            # ✅ 只有子类重写了 from_orm 才调用
            if custom_from_orm and custom_from_orm is not base_from_orm:
                return cls.from_orm(data)

            # ✅ 正常 v2 方式
            return cls.model_validate(data)

        # ✅ dict
        if isinstance(data, dict):
            return cls(**data)

        raise TypeError(f"Unsupported type for {cls.__name__}: {type(data)}")

    # --------------------------------------------------
    # 可选：格式化时间字段输出
    # --------------------------------------------------
    @field_serializer("create_time", "update_time")
    def _format_time(self, dt: datetime, _info):
        return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None

class PageQuery:
    def __init__(
        self,
        page: int = Query(1, ge=1),
        size: int = Query(10, ge=1, le=100)
    ):
        self.page = page
        self.size = size

class FlashSaleTimeSchema(BaseModel):
    flash_end_time: int | None = None
    server_time: int | None = None
    status:str | None = None

    DATETIME_FORMAT: ClassVar[str] = "%Y-%m-%d %H:%M:%S"

    @staticmethod
    def _format_ts(ts: int | None):
        if ts is None:
            return None
        # 毫秒 → 秒 → datetime
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        return dt.strftime(FlashSaleTimeSchema.DATETIME_FORMAT)

    @computed_field
    def flash_end_time_format(self) -> str | None:
        return self._format_ts(self.flash_end_time)

    @computed_field
    def server_time_format(self) -> str | None:
        return self._format_ts(self.server_time)