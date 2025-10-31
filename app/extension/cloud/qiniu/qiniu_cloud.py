"""
# @Time    : 2025/11/1 1:03
# @Author  : Pedro
# @File    : qiniu_cloud.py
# @Software: PyCharm

七牛云上传工具（FastAPI / Pedro-Core 版本）
✅ 自动读取 settings.yml
✅ 单文件 & 多文件上传
✅ 返回 CDN URL
"""

import qiniu
from qiniu import Auth, put_data
from app.config.settings_manager import get_current_settings
from uuid import uuid4

settings = get_current_settings()
cfg = settings.qiniu  # 你 settings.yml 里的 qiniu 节点

QINIU_ACCESS_KEY = cfg.access_key
QINIU_SECRET_KEY = cfg.secret_key
QINIU_BUCKET     = cfg.bucket
QINIU_CDN        = cfg.cdn


def qiniu_upload_bytes(file_bytes: bytes, file_path: str) -> str:
    """
    上传字节流到七牛（同步）
    """
    if not all([QINIU_ACCESS_KEY, QINIU_SECRET_KEY, QINIU_BUCKET, QINIU_CDN]):
        raise ValueError("❌ 七牛云配置缺失，请检查 settings.yml")

    q = Auth(QINIU_ACCESS_KEY, QINIU_SECRET_KEY)
    token = q.upload_token(QINIU_BUCKET, file_path, 3600)

    ret, info = put_data(token, file_path, file_bytes)

    if info.status_code != 200:
        raise Exception(f"⚠️ 上传失败: {info}")

    cdn_url = f"{QINIU_CDN.rstrip('/')}/{file_path.lstrip('/')}"
    return cdn_url


async def qiniu_upload_file(file, save_path: str):
    """
    FastAPI UploadFile 异步读取 + 上传
    """
    file_bytes = await file.read()
    return qiniu_upload_bytes(file_bytes, save_path)


async def qiniu_upload_batch(files, prefix: str = "upload/"):
    """
    ✅ 多图上传
    files: List[UploadFile]
    return: { filename: cdn_url }
    """
    results = {}

    for file in files:
        filename = file.filename
        save_path = f"{prefix.rstrip('/')}/{uuid4()}{filename}"
        url = await qiniu_upload_file(file, save_path)
        results[filename] = url

    return results
