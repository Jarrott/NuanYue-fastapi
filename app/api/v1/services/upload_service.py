import aiohttp
import base64

from fastapi import UploadFile


async def upload_to_firebase(file: UploadFile):
    url = "https://uploadimage-379230954149.us-central1.run.app"

    # 读取文件并转为 base64
    file_bytes = await file.read()
    encoded = base64.b64encode(file_bytes).decode("utf-8")

    payload = {
        "file": encoded,  # 👈 必须叫 file!!!
        "filename": file.filename
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            text = await resp.text()
            try:
                return await resp.json()
            except:
                return {"error": "not json", "raw": text, "status": resp.status}
