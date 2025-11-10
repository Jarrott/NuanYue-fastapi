# @Time    : 2025/11/11 01:30
# @Author  : Pedro
# @File    : response.py
# @Software: PyCharm
"""
Pedro-Core 通用响应模型（自动过滤 + ORM兼容 + 分页支持 + Decimal安全）
✅ 统一响应封装：success / fail / page
✅ 自动识别 ORM / Pydantic / dict / list
✅ Firestore, Decimal, datetime, bytes 全兼容
✅ 支持 schema 参数自动过滤响应字段（含 Decimal 容错）
✅ Python 3.13 + Pydantic v2 完全兼容
"""

import json
import datetime
from decimal import Decimal
from typing import Any, Generic, Optional, Type, TypeVar, Iterable
from pydantic import BaseModel, Field, ConfigDict
from pydantic.generics import GenericModel
from starlette.responses import JSONResponse

T = TypeVar("T")

# =========================================================
# 🔰 Firestore DatetimeWithNanoseconds 安全导入（可选）
# =========================================================
try:
    from google.cloud.firestore_v1._helpers import DatetimeWithNanoseconds
except ImportError:
    DatetimeWithNanoseconds = None


# =========================================================
# ✅ 通用序列化函数
# =========================================================
def serialize(data: Any) -> Any:
    """递归序列化各种复杂对象到 JSON 安全格式"""
    if DatetimeWithNanoseconds and isinstance(data, DatetimeWithNanoseconds):
        return data.isoformat()

    if isinstance(data, (datetime.datetime, datetime.date)):
        return data.isoformat()

    if isinstance(data, Decimal):
        return float(data)

    if isinstance(data, (bytes, bytearray)):
        return data.decode("utf-8", errors="ignore")

    if isinstance(data, set):
        return list(data)

    if isinstance(data, BaseModel):
        return serialize(data.model_dump())

    if hasattr(data, "__table__"):  # SQLAlchemy ORM
        try:
            return {c.key: serialize(getattr(data, c.key)) for c in data.__table__.columns}
        except Exception:
            return str(data)

    if isinstance(data, (list, tuple)):
        return [serialize(i) for i in data]

    if isinstance(data, dict):
        return {k: serialize(v) for k, v in data.items()}

    return data


# =========================================================
# ✅ Schema 过滤工具（含 Decimal 自动兼容）
# =========================================================
def _filter_with_schema(schema: Type[BaseModel], value: Any) -> Any:
    """用 Pydantic schema 过滤任意对象（支持 ORM、dict、BaseModel、list）"""
    if value is None:
        return None

    def safe_validate(v):
        try:
            # 使用 strict=False + from_attributes=True 允许自动类型转换（Decimal→float、date→str）
            return schema.model_validate(v, from_attributes=True, strict=False).model_dump()
        except Exception:
            # fallback：先序列化，再重新 model_validate
            return schema.model_validate(serialize(v), strict=False).model_dump()

    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict, BaseModel)):
        return [safe_validate(v) for v in value]
    if isinstance(value, BaseModel):
        return safe_validate(value.model_dump())
    return safe_validate(value)


# =========================================================
# ✅ Pedro JSON Response
# =========================================================
class PedroJSONResponse(JSONResponse):
    """统一 JSONResponse 编码（UTF-8 + 禁止 ASCII 转义）"""
    def render(self, content: Any) -> bytes:
        try:
            return json.dumps(
                content,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except Exception:
            return json.dumps(
                {"code": 500, "msg": "JSON 序列化失败", "data": str(content)},
                ensure_ascii=False
            ).encode("utf-8")


# =========================================================
# ✅ PedroResponse 泛型模型（主类）
# =========================================================
class PedroResponse(GenericModel, Generic[T]):
    code: int = Field(default=0, description="状态码")
    msg: str = Field(default="success", description="消息")
    data: Optional[T] = Field(default=None, description="数据体")

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        from_attributes=True,
        validate_by_name=True,
    )

    # -----------------------------------------------------
    # 🧠 自动转换 ORM/BaseModel/Dict
    # -----------------------------------------------------
    @staticmethod
    def _safe_model_dump(obj: Any) -> Any:
        """智能安全序列化对象"""
        try:
            if obj is None:
                return None

            if isinstance(obj, BaseModel):
                return obj.model_dump()

            if hasattr(obj, "__table__"):
                return {c.key: serialize(getattr(obj, c.key)) for c in obj.__table__.columns}

            if isinstance(obj, (dict, list, tuple, set)):
                return serialize(obj)

            return serialize(obj)
        except Exception:
            return serialize(obj)

    # -----------------------------------------------------
    # ✅ 成功响应（支持 schema 自动过滤）
    # -----------------------------------------------------
    @classmethod
    def success(
        cls,
        data: Optional[Any] = None,
        msg: str = "success",
        code: int = 0,
        schema: Optional[Type[BaseModel]] = None,
    ):
        """统一成功响应"""
        try:
            if schema is not None and data is not None:
                data = _filter_with_schema(schema, data)
            elif isinstance(data, list):
                data = [cls._safe_model_dump(i) for i in data]
            elif data is not None:
                data = cls._safe_model_dump(data)

            payload = {"code": code, "msg": msg, "data": serialize(data)}
        except Exception as e:
            payload = {"code": 500, "msg": f"响应构建失败: {e}", "data": None}

        return PedroJSONResponse(content=payload)

    # -----------------------------------------------------
    # ❌ 错误响应
    # -----------------------------------------------------
    @classmethod
    def fail(cls, msg: str = "failed", code: int = 1, data: Any = None):
        """统一错误响应"""
        try:
            payload = {"code": code, "msg": msg}
            if data is not None:
                payload["data"] = serialize(data)
        except Exception:
            payload = {"code": 500, "msg": "错误响应构建失败", "data": None}

        return PedroJSONResponse(content=payload)

    # -----------------------------------------------------
    # 📄 分页响应（支持 schema 自动过滤）
    # -----------------------------------------------------
    @classmethod
    def page(
        cls,
        *,
        items: Any,
        total: int,
        page: int,
        size: int,
        msg: str = "success",
        code: int = 0,
        schema: Optional[Type[BaseModel]] = None,
    ):
        """分页统一输出"""
        try:
            if schema is not None and items is not None:
                items = _filter_with_schema(schema, items)
            elif isinstance(items, list):
                items = [cls._safe_model_dump(i) for i in items]
            elif items is not None:
                items = cls._safe_model_dump(items)
            else:
                items = []

            data = {
                "items": serialize(items),
                "total": total,
                "page": page,
                "size": size,
            }
            payload = {"code": code, "msg": msg, "data": data}
        except Exception as e:
            payload = {
                "code": 500,
                "msg": f"分页响应构建失败: {e}",
                "data": {"items": [], "total": total, "page": page, "size": size},
            }

        return PedroJSONResponse(content=payload)
