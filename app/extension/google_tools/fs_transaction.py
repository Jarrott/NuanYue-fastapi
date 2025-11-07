"""
Firestore 事务与原子操作封装层
------------------------------------------------------
✅ 复用 FirestoreService 的实例 (fs_service.db)
✅ 补充: SERVER_TIMESTAMP / Increment / transactional / run_transaction / doc()
✅ 为 WalletSecureService 等高层服务提供完整事务能力
"""

from google.cloud.firestore_v1 import SERVER_TIMESTAMP as _SERVER_TIMESTAMP
from firebase_admin.firestore import firestore as fb
from app.extension.google_tools import firestore as firestore_module

# ✅ 复用现有 FirestoreService 单例
fs_service = firestore_module.fs_service
db = fs_service.db

# ======================================================
# ✅ 基本操作导出
# ======================================================
SERVER_TIMESTAMP = _SERVER_TIMESTAMP
Increment = fb.Increment
transactional = fb.transactional


def doc(path: str):
    """返回文档引用"""
    return db.document(path)


# ======================================================
# ✅ run_transaction 兼容封装
# ======================================================
def run_transaction(tx_func):
    """
    兼容 firebase_admin 无 run_transaction 的情况
    内部调用 db.transaction()，自动执行事务函数
    用法：
        @transactional
        def _tx(transaction): ...
        result = run_transaction(_tx)
    """
    transaction = db.transaction()
    return tx_func(transaction)
