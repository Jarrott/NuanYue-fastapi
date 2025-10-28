"""
# @Time    : 2025/10/5 9:59
# @Author  : Pedro
# @File    : user.py
# @Software: PyCharm
"""
import re
from typing import List, Optional, Any, Dict
from pydantic import Field, validator

from app.api.cms.schema import GroupIdListSchema, EmailSchema
from app.pedro.exception import BaseModel, ParameterError


class UserRegisterSchema(BaseModel):
    # username: constr(regex=r'^[a-zA-Z0-9_]{2,10}$') = Field(description="用户名")
    username: str = Field(description="用户名", min_length=2, max_length=50)
    password: str = Field(description="密码", min_length=6, max_length=22)
    group_ids: List[int] = Field(description="用户组,前端客户默认3", default=[3])
    inviter_code: str = Field(default=None)

    # inviter_code: str = Field(description="密码", min_length=6, max_length=22, default=None)


class UserInformationUpdateSchema(BaseModel):
    information: Optional[Dict[str, Any]] = Field(None, description="用户扩展字段（JSON）")


class LoginSchema(BaseModel):
    username: str = Field(description="用户名")
    password: str = Field(description="密码")
    captcha: Optional[str] = Field(description="验证码", default=None)


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

# class ChangePasswordSchema(ResetPasswordSchema):
#     old_password: str = Field(description="旧密码")
