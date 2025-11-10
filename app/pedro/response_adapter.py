# @Time    : 2025/11/10 09:10
# @Author  : Pedro
# @File    : response_adapter.py
# @Software: PyCharm
"""
🧩 Pedro-Core Response Adapter
统一适配各种返回值（list / dict / JSONResponse / Firestore / ORM）到 PedroResponse
----------------------------------------------------------
✅ 自动提取 data / items
✅ 自动展开 JSONResponse / PedroResponse
✅ Firestore DatetimeWithNanoseconds → ISO
✅ 一行封装分页输出
"""

import json
from google.cloud.firestore_v1 import _helpers
from starlette.responses import JSONResponse
from app.pedro.response import PedroResponse, serialize


class PedroResponseAdapter:
    """业务层结果 → PedroResponse 的统一适配器"""

    # -------------------------------------------
    # 🔧 自动提取 items
    # -------------------------------------------
    @staticmethod
    def extract_items(result):
        if isinstance(result, list):
            return result

        if isinstance(result, dict):
            # 兼容 data/items 层
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

    # -------------------------------------------
    # 🔧 Firestore 时间戳转换
    # -------------------------------------------
    @staticmethod
    def normalize(obj):
        """递归处理 Firestore DatetimeWithNanoseconds"""
        if isinstance(obj, _helpers.DatetimeWithNanoseconds):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: PedroResponseAdapter.normalize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [PedroResponseAdapter.normalize(v) for v in obj]
        return obj

    # -------------------------------------------
    # ✅ 一键分页包装
    # -------------------------------------------
    @classmethod
    def page(cls, result, page: int = 1, size: int = 20, msg="success"):
        items = cls.extract_items(result)
        normalized = [cls.normalize(i) for i in items]
        return PedroResponse.page(items=normalized, total=len(normalized), page=page, size=size, msg=msg)

    # -------------------------------------------
    # ✅ 一键成功包装（单数据）
    # -------------------------------------------
    @classmethod
    def success(cls, result, msg="success"):
        normalized = cls.normalize(serialize(result))
        return PedroResponse.success(data=normalized, msg=msg)
