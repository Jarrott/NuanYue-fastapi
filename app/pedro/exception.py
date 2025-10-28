# -*- coding: utf-8 -*-
"""
@Time    : 2025/10/26 4:25
@Author  : Pedro
@File    : exception.py
@Software: PyCharm
"""
import traceback
from typing import Optional, List
from fastapi import Request, logger
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

from app.extension.i18n.i18n_exception import translate_message


# ======================================================
# 🚨 通用异常模型
# ======================================================
class APIExceptionModel(BaseModel):
    msg: str = "sorry, we made a mistake (*￣︶￣)!"
    error_code: int = 999
    request: Optional[str] = None


# ======================================================
# 🚨 基础异常基类
# ======================================================
class APIException(Exception):
    def __init__(self, msg="sorry, we made a mistake (*￣︶￣)!", error_code=999, http_code=400):
        self.msg = msg
        self.error_code = error_code
        self.http_code = http_code

    def to_dict(self, request: Optional[Request] = None):
        req_str = f"{request.method} {request.url.path}" if request else None
        return APIExceptionModel(msg=self.msg, error_code=self.error_code, request=req_str).dict()


# ======================================================
# 🎯 具体异常类型
# ======================================================
class NotFound(APIException):
    def __init__(self, msg="资源未找到", error_code=1001):
        super().__init__(msg, error_code, http_code=404)


class ParameterError(APIException):
    def __init__(self, msg="参数错误", error_code=1002):
        super().__init__(msg, error_code, http_code=400)


class AuthFailed(APIException):
    def __init__(self, msg="认证失败", error_code=1003):
        super().__init__(msg, error_code, http_code=401)


class Forbidden(APIException):
    def __init__(self, msg="权限不足", error_code=1004):
        super().__init__(msg, error_code, http_code=403)


class Success(APIException):
    def __init__(self, msg="执行成功", error_code=2002):
        super().__init__(msg, error_code, http_code=200)


class HTTPException(APIException):
    def __init__(self, msg="出现了一些问题", error_code=3002):
        super().__init__(msg, error_code, http_code=300)


class InternalServerError(APIException):
    def __init__(self, msg="服务器内部错误", error_code=5001):
        super().__init__(msg, error_code, http_code=500)


class UnAuthentication(APIException):
    code = 401
    message = "Authentication Failed"
    message_code = 10010


# ======================================================
# ⚙️ 全局异常处理器注册函数
# ======================================================
#

def register_exception_handlers(app):
    """注册全局异常处理器"""

    # ✅ 捕获自定义 APIException
    @app.exception_handler(APIException)
    async def api_exception_handler(request: Request, exc: APIException):
        return await build_error_response(
            request, exc.msg, exc.error_code, exc.http_code
        )

    # ✅ 捕获 Pydantic 校验错误（422）
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        first_err = exc.errors()[0] if exc.errors() else {}
        msg = first_err.get("msg", "参数错误")
        return await build_error_response(request, msg, 1005, 422)

    # ✅ 捕获系统未处理异常（500）
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        logger.logger.error(f"[UnhandledException] {request.method} {request.url.path}\n{tb_str}")
        return await build_error_response(request, "服务器内部错误，请稍后重试", 9999, 500)


async def build_error_response(request: Request, msg: str, error_code: int, http_code: int):
    lang = request.headers.get("Accept-Language", "zh").split(",")[0].strip().lower()
    msg = await translate_message(msg, lang[:2])

    model = APIExceptionModel(
        msg=msg,
        error_code=error_code,
        request=f"{request.method} {request.url.path}"
    )
    content = model.model_dump() if hasattr(model, "model_dump") else model.dict()
    return JSONResponse(status_code=http_code, content=content)
