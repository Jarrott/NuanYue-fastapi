from fastapi import Request
from app.extension.i18n.i18n_exception import detect_language


async def get_lang(request: Request, uid: int | None = None, text: str = None) -> str:
    """
    🌍 获取用户语言（智能优先级）：
    ------------------------------------------------
    1）用户账户语言设置
    2）App-Language / X-Language
    3）Accept-Language (浏览器/客户端)
    4）自动语言识别 detect_language(text)
    5）默认 zh
    ------------------------------------------------
    """

    # 1）用户语言设置优先
    if uid:
        from app.api.cms.model.user import User
        user = await User.get(id=uid)
        if user and user.extra and user.extra.get("language"):
            return user.extra["language"].lower()

    # 2）APP 请求头
    app_lang = request.headers.get("App-Language") or request.headers.get("X-Language")
    if app_lang:
        return app_lang.lower()[:2]

    # 3）浏览器 Accept-Language
    header_lang = request.headers.get("Accept-Language", "").split(";")[0].strip().lower()
    if header_lang:
        return header_lang[:2]

    # 4）AI 检测兜底
    if text:
        detected = await detect_language(text)
        if detected:
            return detected[:2]

    # 5）最终 fallback
    return "en"
