# -*- coding: utf-8 -*-
"""
Pedro exception system - enhanced ExceptionGroup support
"""
import traceback
import uuid
from typing import Optional
from fastapi import Request, logger
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from app.extension.i18n.i18n_exception import translate_message

try:
    ExceptionGroup  # noqa
except NameError:
    from exceptiongroup import ExceptionGroup


class APIExceptionModel(BaseModel):
    msg: str = "sorry, we made a mistake (*￣︶￣)!"
    error_code: int = 999
    request: Optional[str] = None
    trace_id: Optional[str] = None


class APIException(Exception):
    def __init__(self, msg="sorry, we made a mistake (*￣︶￣)!", error_code=999, http_code=400):
        self.msg = msg
        self.error_code = error_code
        self.http_code = http_code

    def to_dict(self, request: Optional[Request] = None):
        req_str = f"{request.method} {request.url.path}" if request else None
        return APIExceptionModel(msg=self.msg, error_code=self.error_code, request=req_str).dict()


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


async def build_error_response(request: Request, msg: str, error_code: int, http_code: int, trace_id=None):
    lang = request.headers.get("Accept-Language", "zh").split(",")[0].strip().lower()
    msg = await translate_message(msg, lang[:2])
    trace_id = trace_id or uuid.uuid4().hex[:8]

    model = APIExceptionModel(
        msg=msg,
        error_code=error_code,
        request=f"{request.method} {request.url.path}",
        trace_id=trace_id,
    )
    content = model.model_dump() if hasattr(model, "model_dump") else model.dict()
    return JSONResponse(status_code=http_code, content=content)


# ✅ 新增：安全错误消息函数（不暴露内部报错内容）
def _safe_err_msg(exc: Exception) -> str:
    if isinstance(exc, APIException):
        return exc.msg
    return "服务器内部异常，请稍后重试"


def register_exception_handlers(app):

    @app.exception_handler(APIException)
    async def api_exception_handler(request: Request, exc: APIException):
        return await build_error_response(request, exc.msg, exc.error_code, exc.http_code)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        first_err = exc.errors()[0] if exc.errors() else {}
        msg = first_err.get("msg", "参数错误")
        return await build_error_response(request, msg, 1005, 422)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        trace_id = uuid.uuid4().hex[:8]

        # ✅处理 ExceptionGroup / BaseExceptionGroup
        if isinstance(exc, BaseExceptionGroup) or type(exc).__name__.endswith("ExceptionGroup"):
            inner = exc.exceptions[0] if hasattr(exc, "exceptions") and exc.exceptions else exc

            if isinstance(inner, APIException):
                return await build_error_response(request, inner.msg, inner.error_code, inner.http_code, trace_id)

            tb_str = "".join(traceback.format_exception(type(inner), inner, inner.__traceback__))
            logger.logger.error(f"[ExceptionGroup] TraceID={trace_id}\n{tb_str}")

            # ✅ 不用 str(inner)，避免泄露内部信息
            return await build_error_response(request, _safe_err_msg(inner), 9999, 500, trace_id)

        # ✅ 普通异常 fallback
        tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        logger.logger.error(f"[Unhandled] TraceID={trace_id} {request.method} {request.url.path}\n{tb_str}")

        safe_msg = _safe_err_msg(exc)
        return await build_error_response(request, safe_msg, 9999, 500, trace_id)

    @app.middleware("http")
    async def websocket_origin_middleware(request, call_next):
        # websocket 直接放行
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        return await call_next(request)
