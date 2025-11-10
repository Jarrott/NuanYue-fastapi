# @Time    : 2025/11/11 00:48
# @Author  : Pedro
# @File    : response_adapter.py
# @Software: PyCharm
"""
🧩 Pedro-Core Response Adapter（新版）
----------------------------------------------------------
统一适配各种返回值 → PedroJSONResponse
✅ 自动提取 data/items
✅ 自动展开 JSONResponse / PedroResponse
✅ Firestore DatetimeWithNanoseconds → ISO
✅ Decimal → float
✅ 一键分页包装（PedroResponse.page）
"""

import json
from decimal import Decimal
from typing import Any
from starlette.responses import JSONResponse
from google.cloud.firestore_v1 import _helpers
from app.pedro.response import PedroJSONResponse, serialize, PedroResponse


class PedroResponseAdapter:
    """业务层结果 → PedroJSONResponse 的统一适配器"""

    # -----------------------------------------------------
    # 🔍 提取 items
    # -----------------------------------------------------
    @staticmethod
    def extract_items(result):
        """智能提取 data/items 内容"""
        if isinstance(result, list):
            return result

        if isinstance(result, dict):
            if "data" in result:
                data_block = result["data"]
                if isinstance(data_block, dict) and "items" in data_block:
                    return data_block["items"]
                return data_block
            return result.get("items", [])

        if isinstance(result, JSONResponse):
            try:
                body = json.loads(result.body.decode())
                if "data" in body:
                    data_block = body["data"]
                    if isinstance(data_block, dict) and "items" in data_block:
                        return data_block["items"]
                    return data_block
                return body.get("items", [])
            except Exception:
                return []

        return []

    # -----------------------------------------------------
    # 🔧 类型规范化
    # -----------------------------------------------------
    @staticmethod
    def normalize(obj: Any):
        """递归处理 Firestore / Decimal / bytes / datetime 等类型"""
        if isinstance(obj, _helpers.DatetimeWithNanoseconds):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="ignore")
        if isinstance(obj, dict):
            return {k: PedroResponseAdapter.normalize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [PedroResponseAdapter.normalize(v) for v in obj]
        return obj

    # -----------------------------------------------------
    # ✅ 分页包装
    # -----------------------------------------------------
    @classmethod
    def page(cls, result, page: int = 1, size: int = 20, msg: str = "success"):
        """
        🔢 Pedro-Core 通用分页适配器
        -------------------------------------
        ✅ 自动识别 result 类型（list / Query / JSONResponse）
        ✅ 自动 total 统计（切片前）
        ✅ 自动分页切片
        ✅ 自动 normalize + serialize（兼容 Decimal / Firestore / datetime）
        ✅ 统一返回 PedroResponse.page()
        """

        # 1️⃣ 提取 items
        items = cls.extract_items(result)
        if not isinstance(items, list):
            try:
                items = list(items)
            except Exception:
                items = []

        # 2️⃣ 总数统计（切片前）
        total = len(items)

        # 3️⃣ 参数安全化
        try:
            page = max(int(page or 1), 1)
            size = max(int(size or 20), 1)
        except Exception:
            page, size = 1, 20

        # 4️⃣ 分页切片
        start = (page - 1) * size
        end = start + size
        page_items = items[start:end]

        # 5️⃣ 序列化 + Firestore/Decimal 兼容
        normalized_items = [cls.normalize(serialize(i)) for i in page_items]

        # 6️⃣ 返回 PedroResponse.page（自动 JSON 序列化）
        return PedroResponse.page(
            items=normalized_items,
            total=total,
            page=page,
            size=size,
            msg=msg,
        )

    # -----------------------------------------------------
    # ✅ 单项成功包装
    # -----------------------------------------------------
    @classmethod
    def success(cls, result, msg="success"):
        """返回统一成功响应（PedroJSONResponse）"""
        normalized = cls.normalize(serialize(result))
        payload = {"code": 0, "msg": msg, "data": normalized}
        return PedroJSONResponse(content=payload)
