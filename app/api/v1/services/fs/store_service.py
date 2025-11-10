from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from app.pedro.response import PedroResponse
from app.extension.google_tools.firebase_admin_service import fs


class StoreServiceFS:

    @staticmethod
    async def list_stores(limit: int = 20):
        db = fs

        query = (db.collection_group("store")
                 .where(filter=FieldFilter("status", "==", "approved")).
                 order_by(
            "create_time", direction=firestore.Query.DESCENDING
        ).limit(limit))

        docs = query.stream()
        stores = []
        for doc in docs:
            if doc.id == "profile":
                data = doc.to_dict()
                data["uid"] = doc.reference.parent.parent.id  # 反推 user id
                stores.append(data)

        print(f"✅ Found {len(stores)} profile docs")
        return stores
