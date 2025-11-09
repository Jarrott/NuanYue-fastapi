from sqlalchemy import Column, String, Boolean, JSON, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.pedro.interface import InfoCrud


class VirtualUser(InfoCrud):
    __tablename__ = "virtual_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(64), unique=True, nullable=False)
    email = Column(String(128), unique=True)
    postcode = Column(String(128))
    locale = Column(String(256))
    region = Column(String(256))
    address = Column(String(256))
    is_bot = Column(Boolean, default=True)
