# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/13 20:10
# @Author  : Pedro
# @File    : send_email_ycloud_httpx.py
# @Software: PyCharm
"""
import httpx
from app.util.build_email_html import build_signup_email
from app.pedro.config import get_current_settings


async def send_signup_email(username: str, recipient: str, token: str):
    html_content = build_signup_email(username, f"https://yoyo-global.com/activate?token={token}")
    settings = get_current_settings()
    payload = {
        "contentType": "text/html",
        "from": "admin@sap.global.qi-yue.vip",
        "to": recipient,
        "subject": f"Welcome {username}, activate your YOYO account",
        "content": html_content
    }

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": settings.ycloud.apikey,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            "https://api.ycloud.com/v2/emails",
            json=payload,
            headers=headers
        )

    if response.is_success:
        print("✅ 邮件发送成功:", response.json())
    else:
        print("❌ 邮件发送失败:", response.status_code, response.text)
