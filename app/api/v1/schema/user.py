"""
# @Time    : 2025/10/5 9:59
# @Author  : Pedro
# @File    : user.py
# @Software: PyCharm
"""
import re
from datetime import datetime
from typing import List, Optional, Any, Dict, Self
from pydantic import Field, validator, EmailStr, field_serializer
from user_agents import parse as ua_parse
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


class UserRegisterSchema(BaseModel):
    # username: constr(regex=r'^[a-zA-Z0-9_]{2,10}$') = Field(description="用户名")
    username: str = Field(description="用户名", min_length=2, max_length=50)
    password: str = Field(description="密码", min_length=6, max_length=22)
    group_ids: List[int] = Field(description="用户组,前端客户默认3", default=[3])
    inviter_code: str = Field(default=None)


class UserInformationUpdateSchema(BaseModel):
    information: Optional[Dict[str, Any]] = Field(None, description="用户扩展字段（JSON）")


class LoginSchema(BaseModel):
    username: str = Field(description="用户名")
    password: str = Field(description="密码")
    captcha: Optional[str] = Field(description="验证码", default=None)
    remember_me: str = Field(description="是否信任此设备", default="false")


class LoginTokenSchema(BaseModel):
    access_token: str = Field(description="access_token")
    refresh_token: str = Field(description="refresh_token")


class CaptchaSchema(BaseModel):
    image: str = Field("", description="验证码图片base64编码")
    tag: str = Field("", description="验证码标记码")


class PermissionNameSchema(BaseModel):
    name: str = Field(description="权限名称")


class PermissionModuleSchema(BaseModel):
    module: List[PermissionNameSchema] = Field(description="权限模块")


class UserBaseInfoSchema(EmailSchema):
    nickname: Optional[str] = Field(description="用户昵称", min_length=2, max_length=10)
    avatar: Optional[str] = Field(description="头像url")


class UserSchema(UserBaseInfoSchema):
    id: int = Field(description="用户id")
    username: str = Field(description="用户名")
    extra: Optional[Dict[str, Any]] = Field(None, description="用户扩展字段 JSON")

    class Config:
        model_config = {
            "from_attributes": True
        }
        extra = "allow"


class UserPermissionSchema(UserSchema):
    admin: bool = Field(description="是否是管理员")
    permissions: List[PermissionModuleSchema] = Field(description="用户权限")


class UserInformationSchema(BaseSchema):
    id: int
    username: Optional[str] = None
    nickname: Optional[str] = None
    email: Optional[str] = None
    avatar: Optional[str] = None
    create_time: Optional[datetime] = Field(None, alias="create_time")

    # ✅ 从 extra 中筛选部分字段展示
    vip_status: Optional[bool] = None
    vip_expire_at: Optional[datetime] = None
    lang: Optional[str] = None
    theme: Optional[str] = None
    invite_code: Optional[str] = None
    device_info: Optional[list[dict]] = None

    class Config:
        from_attributes = True  # ✅ 代替 orm_mode
        validate_by_name = True  # ✅ 代替 allow_population_by_field_name

    @classmethod
    def from_orm(cls, user):
        """✅ ORM → Response 模型"""
        avatar = getattr(user, "_avatar", None)

        # ✅ 提取安全的 extra 信息
        extra = user.extra or {}
        referral = extra.get("referral") or {}
        setting = extra.get("settings") or {}
        sensitive = extra.get("sensitive") or {}



        return cls(
            id=user.id,
            username=user.username,
            nickname=user.nickname,
            email=user.email,
            avatar=avatar,
            create_time=user.create_time,
            vip_status=extra.get("vip_status"),
            vip_expire_at=extra.get("vip_expire_at"),
            lang=setting.get("lang"),
            theme=setting.get("theme"),
            invite_code=referral.get("invite_code"),
            device_info=sensitive.get("login_devices")
        )


class OTCDepositSchema(BaseModel):
    amount: float
    token: str = "USDT"
    proof_image: str  # 图片URL

class UserAgentSchema(BaseModel):
    device: str
    browser: str
    os: str
    raw: str

    @classmethod
    def from_ua(cls, ua_string: str):
        ua = ua_parse(ua_string)
        return cls(
            device=ua.device.family or "Unknown",
            browser=ua.browser.family or "Unknown",
            os=ua.os.family or "Unknown",
            raw=ua_string
        )