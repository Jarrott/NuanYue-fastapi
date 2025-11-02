"""
# @Time    : 2025/11/2 18:56
# @Author  : Pedro
# @File    : response.py
# @Software: PyCharm
"""
from typing import Generic, TypeVar, Optional, Any
from pydantic import ConfigDict, Field, BaseModel
from pydantic.generics import GenericModel
from starlette.responses import JSONResponse
from sqlalchemy.orm import DeclarativeBase

T = TypeVar("T")


# ✅ 通用序列化方法
def serialize(data: Any):
    # Pydantic 模型
    if isinstance(data, BaseModel):
        return data.model_dump()

    # SQLAlchemy Base Model
    if hasattr(data, "__table__"):  # ORM 对象
        return {c.key: getattr(data, c.key) for c in data.__table__.columns}

    # List / Tuple
    if isinstance(data, (list, tuple)):
        return [serialize(i) for i in data]

    # dict
    if isinstance(data, dict):
        return {k: serialize(v) for k, v in data.items()}

    # 基础类型 (int str bool float None)
    return data


# =========================================================
# ✅ 通用响应模型（带自动序列化）
# =========================================================
class PedroResponse(GenericModel, Generic[T]):
    code: int = Field(default=0, description="状态码")
    msg: str = Field(default="success", description="提示信息")

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        from_attributes=True,
        validate_by_name=True
    )

    @classmethod
    def success(cls, data: Optional[T] = None, msg: str = "success", code: int = 0):
        resp = {"code": code, "msg": msg}
        if data is not None:
            resp["data"] = serialize(data)
        return JSONResponse(content=resp)

    @classmethod
    def fail(cls, msg: str = "failed", code: int = 1):
        return JSONResponse(content={"code": code, "msg": msg})

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
    ):
        payload = {
            "code": code,
            "msg": msg,
            "data": {
                "items": serialize(items),   # ✅ 完全兼容 ORM / Pydantic / dict
                "total": total,
                "page": page,
                "size": size,
            },
        }
        return JSONResponse(content=payload)

