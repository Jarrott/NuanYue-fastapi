from fastapi import UploadFile, File, APIRouter

from app.api.v1.schema.response import OneCreateResponse
from app.extension.cloud.qiniu.qiniu_cloud import qiniu_upload_file, qiniu_upload_batch
from uuid import uuid4
rp = APIRouter(prefix="/upload", tags=['上传服务'])


@rp.post("/one", name="上传服务")
async def upload_single(file: UploadFile = File(...)):
    save_path = f"images/{uuid4()}{file.filename}"
    url = await qiniu_upload_file(file, save_path)
    return OneCreateResponse(url=url)



@rp.post("/batch",name="多图上传")
async def upload_batch(files: list[UploadFile] = File(...)):
    result = await qiniu_upload_batch(files, prefix="images")
    return {"status": "ok", "files": result}
