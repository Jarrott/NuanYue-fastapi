from typing import List, Optional

from pydantic import EmailStr, Field, validator, field_validator

from app.pedro.exception import BaseModel, ParameterError


class EmailSchema(BaseModel):
    email: Optional[str] = Field(description="用户邮箱")

    @field_validator("email")
    def check_email(cls, v, values, **kwargs):
        return EmailStr.validate(v) if v else ""


class ResetPasswordSchema(BaseModel):
    new_password: str = Field(description="新密码", min_length=6, max_length=22)
    confirm_password: str = Field(description="确认密码", min_length=6, max_length=22)

    @field_validator("confirm_password")
    def passwords_match(cls, v, values, **kwargs):
        if v != values["new_password"]:
            raise ParameterError("两次输入的密码不一致，请输入相同的密码")
        return v


class GroupIdListSchema(BaseModel):
    group_ids: List[int] = Field(description="用户组ID列表")

    @field_validator("group_ids", mode="before")
    def validate_group_ids(cls, v):
        if not isinstance(v, list):
            raise ValueError("group_ids 必须为数组")

        for item in v:
            if not isinstance(item, int):
                raise ValueError("group_ids 只能包含整数")

        return v
