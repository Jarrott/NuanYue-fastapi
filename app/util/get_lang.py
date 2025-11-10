"""
# @Time    : 2025/11/10 15:56
# @Author  : Pedro
# @File    : get_lang.py
# @Software: PyCharm
"""
from fastapi import Request

async def get_lang(request: Request) -> str:
    """
    🌐 从请求头中提取语言代码（zh / en / jp 等）
    """
    lang = request.headers.get("Accept-Language", "en").split(";")[0].strip().lower()
    # 只取前2个字符（例如 zh-CN → zh, en-US → en）
    return lang[:2]
