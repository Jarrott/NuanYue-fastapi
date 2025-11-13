# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/13 19:45
# @Author  : Pedro
# @File    : email_template_builder.py
# @Software: PyCharm
"""

def build_signup_email(username: str, activate_link: str) -> str:
    """
    ✉️ 构建注册确认邮件 HTML 模板
    --------------------------------------------------
    :param username: 收件人用户名
    :param activate_link: 激活链接
    :return: HTML 字符串
    """
    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Activate your account</title>
  <style>
    /* Keep styles small and simple; prefer inline for max compatibility, but here for clarity */
    body "{{ background:#f4f4f4; font-family: Arial, Helvetica, sans-serif; margin:0; padding:0; color:#333; }}
    .wrap {{ max-width:600px; margin:36px auto; background:#ffffff; border-radius:8px; overflow:hidden; box-shadow:0 3px 10px rgba(0,0,0,0.06); }}
    .hdr {{ background:#2b7a9e; color:#fff; text-align:center; padding:22px 16px; font-size:20px; font-weight:600; }}
    .body {{ padding:20px 22px; line-height:1.6; font-size:15px; color:#333; }}
    .cta {{ text-align:center; margin:22px 0; }}
    .btn {{ display:inline-block; padding:12px 22px; background:#11607f; color:#fff; text-decoration:none; border-radius:6px; font-weight:600; }}
    .note {{ font-size:13px; color:#666; margin-top:8px; }}
    .footer {{ background:#fafafa; color:#777; font-size:12px; padding:14px 18px; text-align:center; }}
    a.plain {{ color:#11607f; word-break:break-all; }}
  </style>
</head>
<body>
  <div class="wrap" role="article" aria-roledescription="email">
    <div class="hdr">YOYO Global Marketplace</div>
    <div class="body">
      <p>Hi <strong>{username}</strong>,</p>

      <p>Thanks for creating an account at <strong>YOYO Global</strong>. To complete your registration and confirm your email address, please click the button below.</p>

      <div class="cta">
        <a href="{activate_link}" class="btn" target="_blank" rel="noopener noreferrer">Activate account</a>
        <div class="note">If the button above does not work, copy and paste this link into your browser:</div>
        <div class="note"><a class="plain" href="{activate_link}" target="_blank" rel="noopener noreferrer">{activate_link}</a></div>
      </div>

      <p>If you did not request an account or believe this message was sent in error, you can safely ignore it.</p>

      <p>Best regards,<br/>YOYO Support Team</p>
    </div>

    <div class="footer">
      SAP SHOP Global — Cross-border marketplace<br/>
      Need help? Reply to <a href="mailto:support@yoyo-global.com">support@yoyo-global.com</a>
    </div>
  </div>
</body>
</html>

"""
    return html
