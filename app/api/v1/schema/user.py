"""
# @Time    : 2025/10/5 9:59
# @Author  : Pedro
# @File    : user.py
# @Software: PyCharm
"""
import re
import phonenumbers
from phonenumbers import PhoneNumberFormat, region_code_for_country_code
from datetime import datetime
from typing import List, Optional, Any, Dict, Self, Literal, Union
from pydantic import Field, validator, EmailStr, field_serializer, field_validator, computed_field, model_validator
from user_agents import parse as ua_parse
from fastapi import Query
from app.api.cms.schema import GroupIdListSchema, EmailSchema
from app.extension.google_tools.fs_transaction import fs_service
from app.pedro.enums import KYCStatus
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
    phone: str = Field(default=None)
    first_name: str = Field(default=None)
    last_name: str = Field(default=None)
    nickname: str = Field(default=None)
    country: str = Field(default=None)
    register_type: str = Field(default=None)
    email: str = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def normalize_and_extract(cls, data: dict):
        """
        ✅ 自动识别邮箱 / 手机 / 用户名，并提取字段
        -------------------------------------------------
        📧 邮箱: 提取 local_part 作为 username，保留完整 email
        📱 手机: 提取 E.164 格式 + national number，确保唯一性
        🧩 普通用户名: 保留原始值
        """
        if not isinstance(data, dict):
            return data

        value = data.get("username", "").strip()
        if not value:
            return data

        # ============================================================
        # 📧 邮箱注册
        # ============================================================
        if re.match(r"^[^@]+@[^@]+\.[^@]+$", value):
            local_part, domain = value.split("@", 1)
            domain_prefix = domain.split(".")[0][:2].lower()
            base_username = f"{local_part.lower()}_{domain_prefix}"

            data["email"] = value.lower()
            data["identity_type"] = "EMAIL"
            data["username"] = base_username
            return data

        # ============================================================
        # 📱 手机注册（自动识别国家码、national_number）
        # ============================================================
        if value.startswith("+"):
            try:
                phone_obj = phonenumbers.parse(value, None)
                e164 = phonenumbers.format_number(phone_obj, PhoneNumberFormat.E164)
                national = str(phone_obj.national_number)
                country_code = phone_obj.country_code
                region = region_code_for_country_code(country_code)


                data["phone"] = e164
                data["username"] = f"{national}_{region}"
                data["identity_type"] = "PHONE"
                data["country"] = region
                return data

            except phonenumbers.NumberParseException:
                pass  # fallback 到普通用户名逻辑

        # ============================================================
        # 🧩 普通用户名注册
        # ============================================================
        data["identity_type"] = "USERNAME"
        data["username"] = value.lower()
        return data

    @property
    def identity_type(self):
        if "@" in self.username:
            return "EMAIL"
        elif re.match(r"^\+?\d{6,20}$", self.username):
            return "PHONE"
        return "USERNAME"


class UserInformationUpdateSchema(BaseModel):
    information: Optional[Dict[str, Any]] = Field(None, description="用户扩展字段（JSON）")


class LoginSchema(BaseModel):
    username: str = Field(description="用户名 / 邮箱 / 手机号")
    password: str = Field(description="密码")
    captcha: Optional[str] = Field(default=None, description="验证码")
    remember_me: str = Field(default="false", description="是否信任此设备")
    password_encrypted: bool = Field(default=False, description="用户登录密码是否明文传入")

    # 额外解析字段
    email: Optional[str] = None
    phone: Optional[str] = None
    identity_type: Optional[str] = None
    country: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_username(cls, data: dict):
        """
        ✅ 自动识别邮箱 / 手机 / 普通用户名
        让登录时的 username 与注册完全一致（内部标准化）
        --------------------------------------------------
        - 邮箱: 保留完整 email, username = local_part
        - 手机: 转换为国际 E.164 格式, username = national number
        - 普通用户名: 原样转小写
        """
        if not isinstance(data, dict):
            return data

        value = str(data.get("username", "")).strip()
        if not value:
            return data

        # ============================================================
        # 📧 邮箱登录
        # ============================================================
        if re.match(r"^[^@]+@[^@]+\.[^@]+$", value):
            local_part, domain = value.split("@", 1)
            domain_prefix = domain.split(".")[0][:2].lower()
            base_username = f"{local_part.lower()}_{domain_prefix}"

            data["email"] = value.lower()
            data["identity_type"] = "EMAIL"
            data["username"] = base_username
            return data

        # ============================================================
        # 📱 手机号登录 (+81 或 +1 或 +44 等)
        # ============================================================
        if value.startswith("+"):
            try:
                phone_obj = phonenumbers.parse(value, None)
                e164 = phonenumbers.format_number(phone_obj, PhoneNumberFormat.E164)
                national = str(phone_obj.national_number)
                country_code = phone_obj.country_code
                region = region_code_for_country_code(country_code)

                data["phone"] = e164
                data["identity_type"] = "PHONE"
                data["username"] = f"{national}_{region}"
                data["country"] = region
                return data

            except phonenumbers.NumberParseException:
                pass

        # ============================================================
        # 🧩 普通用户名登录
        # ============================================================
        data["identity_type"] = "USERNAME"
        data["username"] = value.lower()
        return data

class LoginTokenSchema(BaseModel):
    access_token: str = Field(description="access_token")
    refresh_token: str = Field(description="refresh_token")


class RefreshTokenSchema(BaseModel):
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
    update_time: Optional[datetime] = Field(None, alias="update_time")

    # ✅ 从 extra 中筛选部分字段展示
    vip_status: Optional[bool] = None
    vip_expire_at: Optional[datetime] = None
    points: Optional[int] = None
    balance: Optional[float] = None
    lang: Optional[str] = None
    theme: Optional[str] = None
    invite_code: Optional[str] = None
    device_info: Optional[list[dict]] = None
    levels: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[int] = None
    birthday: Optional[str] = None
    kyc_status: Optional[bool] = None
    is_merchant: Optional[bool] = None
    kyc_submitted: Optional[bool] = False

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
            update_time=user.update_time,
            points=extra.get("points"),
            balance=extra.get("balance"),
            levels=extra.get("level"),
            vip_status=extra.get("vip_status"),
            vip_expire_at=extra.get("vip_expire_at"),
            phone=extra.get("phone"),
            gender=extra.get("gender"),
            birthday=extra.get("birthday"),
            kyc_status=extra.get("kyc_status") or False,
            is_merchant=extra.get("is_merchant") or False,
            lang=setting.get("lang"),
            theme=setting.get("theme"),
            invite_code=referral.get("invite_code"),
            device_info=sensitive.get("login_devices"),
            kyc_submitted=extra.get("kyc_submitted"),
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


class InformationUpdateSchema(BaseModel):
    avatar: Optional[str] = None
    nickname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[int] = None
    birthday: Optional[str] = None


class ForgotPasswordSendSchema(BaseModel):
    email: Optional[str] = None


class ForgotPasswordResetSchema(BaseModel):
    email: Optional[str] = None
    code: Optional[str] = None
    new_password: Optional[str] = None


class ResetPasswordSendSchema(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    oobCode: Optional[str] = None


class PageQuery:
    def __init__(
            self,
            page: int = Query(1, ge=1),
            size: int = Query(10, ge=1, le=100)
    ):
        self.page = page
        self.size = size


class UserKycSchema(BaseModel):
    # 基础身份
    # Field(...) 省略号表示不能为空
    full_name: str = Field(..., description="用户真实姓名")
    dob: str = Field(..., description="出生日期 YYYY-MM-DD")
    nationality: str = Field(..., description="国籍，例如 CN, JP, US")

    # 证件信息
    id_type: Literal["passport", "national_id", "driver_license"] = Field(..., description="证件类型")
    id_number: str = Field(..., description="证件号码")

    # 证件图片 URL（文件先上传 Storage）
    id_front_url: str = Field(..., description="证件正面图片 URL")
    id_back_url: Optional[str] = Field(None, description="证件背面图片 URL（护照可能没有）")
    selfie_url: str = Field(..., description="手持证件自拍 URL")

    # 联系方式
    contact_email: Optional[EmailStr] = Field(None, description="联系邮箱")
    contact_phone: Optional[str] = Field(None, description="联系电话")
    status: int = Field(default=0, description="认证状态,pending等")
    kyc_status:bool = Field(default=False, description="认证最终结果")

    # 可选备注
    remark: Optional[str] = Field("", description="备注，可输入审核说明")


class ToggleSchema(BaseModel):
    product_id: int = None


class CreateShopSchema(BaseModel):
    product_id: int = None
    amount: float = None
    quantity: int = None


class StoreSchema(BaseModel):
    address: Optional[str] = None
    lang: Optional[str] = None
    email: Optional[str] = None
    avatar: Optional[str] = None
    level: Optional[str] = None
    logo: Optional[str] = None
    store_name: Optional[str] = None


class SearchShopSchema(BaseModel):
    keyword: Optional[str] = None


class SearchHistoryShopSchema(BaseModel):
    keyword: Optional[str] = None

class KycDetailSchema(BaseModel):
    id_back_url: Optional[str] = None
    review_reason: Optional[str] = None
    id_number: Optional[str] = None
    dob: Optional[str] = None  # 出生日期 (YYYY-MM-DD)
    selfie_url: Optional[str] = None
    id_type: Optional[str] = None  # 证件类型 (passport / id_card)
    nationality: Optional[str] = None  # 国籍
    id_front_url: Optional[str] = None
    contact_phone: Optional[str] = None
    full_name: Optional[str] = None
    status: Optional[Union[int, str]] = None
    kyc_status: Optional[bool] = None

    @computed_field
    @property
    def status_label(self) -> str:
        mapping = {
            KYCStatus.PENDING: "pending",
            KYCStatus.APPROVED: "approved",
            KYCStatus.REJECTED: "rejected",
            "pending": "pending",
            "approved": "approved",
            "rejected": "rejected",
            "0": "pending",
            "1": "approved",
            "2": "rejected",
        }

        val = str(self.status).lower() if self.status is not None else ""
        try:
            # 尝试把字符串 "1" 转换成枚举
            key = KYCStatus(int(val)) if val.isdigit() else val
        except (ValueError, TypeError):
            key = val

        return mapping.get(key, "未知状态")