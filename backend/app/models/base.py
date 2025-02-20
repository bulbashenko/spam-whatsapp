from datetime import datetime
from typing import Any, Dict
from uuid import uuid4
from sqlalchemy import Column, DateTime, Boolean, String
from sqlalchemy.sql import func
from app.core.database import Base


class BaseModel(Base):
    __abstract__ = True

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    status = Column(String(50), default="active", nullable=False)

    async def to_dict(self) -> Dict[str, Any]:
        result = {}
        for column in self.__table__.columns:
            try:
                value = getattr(self, column.name)
                if isinstance(value, datetime):
                    result[column.name] = value.isoformat()
                elif column.name == 'status' and hasattr(value, 'value'):
                    # Handle enum status values
                    result[column.name] = value.value.upper()
                else:
                    result[column.name] = value
            except Exception as e:
                result[column.name] = None
        return result

    def soft_delete(self) -> None:
        self.is_active = False
        self.status = "deleted"
        self.updated_at = func.now()

    @property
    def is_deleted(self) -> bool:
        return not self.is_active or self.status == "deleted"