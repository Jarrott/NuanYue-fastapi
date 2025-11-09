"""
Pedro-Core 通用响应模型（自动序列化 + Firestore/ORM/Pydantic兼容）
"""
import json
from typing import Generic, TypeVar, Optional, Any
from pydantic import ConfigDict, Field, BaseModel
from pydantic.generics import GenericModel
from starlette.responses import JSONResponse
import datetime

T = TypeVar("T")

# =========================================================
# 🔰 Firestore DatetimeWithNanoseconds 安全导入（可选）
# =========================================================
try:
    from google.cloud.firestore_v1._helpers import DatetimeWithNanoseconds
except ImportError:
    DatetimeWithNanoseconds = None


# =========================================================
# ✅ 通用安全序列化方法（支持 ORM / Pydantic / Firestore / bytes）
# =========================================================
def serialize(data: Any):
    # Firestore 时间戳
    if DatetimeWithNanoseconds and isinstance(data, DatetimeWithNanoseconds):
        return data.isoformat()

    # Python datetime
    if isinstance(data, datetime.datetime):
        return data.isoformat()

    # bytes → str
    if isinstance(data, (bytes, bytearray)):
        return data.decode("utf-8", errors="ignore")

    # ✅ JSONResponse 兼容
    if isinstance(data, JSONResponse):
        try:
            return json.loads(data.body.decode())  # 取出 JSONResponse 的内容
        except Exception:
            return str(data)

    # Pydantic 模型
    if isinstance(data, BaseModel):
        return data.model_dump()

    # SQLAlchemy ORM
    if hasattr(data, "__table__"):
        return {c.key: serialize(getattr(data, c.key)) for c in data.__table__.columns}

    # List / Tuple
    if isinstance(data, (list, tuple)):
        return [serialize(i) for i in data]

    # dict
    if isinstance(data, dict):
        return {k: serialize(v) for k, v in data.items()}

    # 基础类型 (int, str, bool, float, None)
    return data


# =========================================================
# ✅ PedroResponse 通用响应类（自动 JSON 序列化）
# =========================================================
class PedroResponse(GenericModel, Generic[T]):
    code: int = Field(default=0, description="状态码")
    msg: str = Field(default="success", description="提示信息")

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        from_attributes=True,
        validate_by_name=True,
    )

    # -----------------------------------------------------
    # ✅ 单项成功响应
    # -----------------------------------------------------
    @classmethod
    def success(cls, data: Optional[T] = None, msg: str = "success", code: int = 0):
        resp = {"code": code, "msg": msg}
        if data is not None:
            resp["data"] = serialize(data)
        return JSONResponse(content=resp)

    # -----------------------------------------------------
    # ❌ 失败响应
    # -----------------------------------------------------
    @classmethod
    def fail(cls, msg: str = "failed", code: int = 1):
        return JSONResponse(content={"code": code, "msg": msg})

    # -----------------------------------------------------
    # 📄 分页响应
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
    ):
        payload = {
            "code": code,
            "msg": msg,
            "data": {
                "items": serialize(items),  # ✅ 自动兼容 ORM / Pydantic / Firestore / dict
                "total": total,
                "page": page,
                "size": size,
            },
        }
        return JSONResponse(content=payload)
