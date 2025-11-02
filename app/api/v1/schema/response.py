"""
通用响应模型（Pedro Framework 版）
支持：
- ✅ 泛型响应 PedroResponse[T]
- ✅ 分页响应 PaginatedResponse[T]
- ✅ 错误响应 ErrorResponse
- ✅ 快捷构造 success() / fail()
- ✅ Pydantic v2 完全兼容
"""

from typing import Generic, TypeVar, Optional, List, Any
from pydantic import ConfigDict, Field, BaseModel
from pydantic.generics import GenericModel
from sqlalchemy import Sequence
from starlette.responses import JSONResponse
from app.pedro.response import PedroResponse

T = TypeVar("T")

# =========================================================
# ✅ 分页响应模型（含分页元信息）
# =========================================================
class PaginatedResponse(PedroResponse[List[T]], Generic[T]):
    total: int = Field(default=0, description="总条目数")
    page: int = Field(default=1, description="当前页码")
    size: int = Field(default=10, description="每页大小")

    @classmethod
    def success(
            cls,
            data: Optional[List[T]] = None,
            total: int = 0,
            page: int = 1,
            size: int = 10,
            msg: str = "success",
            code: int = 0
    ):
        return cls(code=code, msg=msg, data=data or [], total=total, page=page, size=size)


# =========================================================
# ❌ 错误响应模型（简化版）
# =========================================================
class ErrorResponse(PedroResponse[None]):
    code: int = Field(default=400, description="错误状态码")
    msg: str = Field(default="请求错误", description="错误信息")


# =========================================================
# ✅ 兼容旧风格定义（如 UserInformationResponse）
# =========================================================
class UserInformationResponse(PedroResponse[T], Generic[T]):
    code: int = Field(default=2002, description="用户信息响应码")
    msg: str = Field(default="success", description="提示信息")
    data: Optional[T] = None


class SuccessResponse(PedroResponse[str]):
    msg: str = "执行成功"
    code: int = 2002
    request: Optional[str] = None


class LoginSuccessResponse(BaseModel):
    access_token: str = ""
    refresh_token: str = ""
    firebase_token: str = ""
    code: int = 2002


class HotCryptoResponse(PedroResponse[list[dict]]):
    access_token: str = ""
    refresh_token: str = ""
    data: Optional[list[dict]] = {}
    code: int = 2002


class GoogleUserInfo(BaseModel):
    uid: str
    email: str
    name: Optional[str] = None
    avatar: Optional[str] = None


class GoogleLoginSuccessResponse(PedroResponse[GoogleUserInfo]):
    access_token: str = ""
    refresh_token: str = ""
    user: Optional[GoogleUserInfo] = None
    code: int = 2002


class DepositCreateResponse(BaseModel):
    code: int = 2002
    msg: str = "提交充值成功"
    order_number: str


class OneCreateResponse(BaseModel):
    # 图片上传
    code: int = 2002
    msg: str = "上传成功"
    url: str


class CarouselListResponse(BaseModel):
    msg: str = "success"
    code: int = 2001
    items: list = None

class ProductResponse(BaseModel):
    id: int
    external_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    price: float
    discount: Optional[float] = None
    rating: Optional[float] = None
    stock: Optional[int] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    sku: Optional[str] = None
    images: Optional[List[str]] = None
    thumbnail: Optional[str] = None
    availability_status: Optional[str] = None
    source: Optional[str] = None
    lang: Optional[str] = "en"

    class Config:
        from_attributes = True  # ✅ 支持 SQLAlchemy ORM model -> schema

class ProductDetailResponse(ProductResponse):
    reviews: Optional[list] = None
    shipping_info: Optional[str] = None
    warranty_info: Optional[str] = None
