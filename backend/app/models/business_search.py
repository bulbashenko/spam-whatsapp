from sqlalchemy import Column, String, Float, Enum, JSON, Index, ForeignKey
from sqlalchemy.orm import relationship
import enum
from datetime import datetime
from .base import BaseModel


class SearchStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BusinessSearch(BaseModel):
    __tablename__ = "business_searches"

    business_type = Column(String(255), nullable=False, index=True)
    location = Column(String(255), nullable=False, index=True)
    radius = Column(Float, default=5000.0)
    
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    min_rating = Column(Float, nullable=True)
    max_price_level = Column(Float, nullable=True)
    open_now = Column(String(5), nullable=True)
    
    status = Column(Enum(SearchStatus), default=SearchStatus.PENDING, nullable=False, index=True)
    results_count = Column(Float, default=0)
    error_message = Column(String(512), nullable=True)
    
    celery_task_id = Column(String(255), nullable=True, unique=True)
    progress = Column(Float, default=0.0)
    last_updated = Column(String(255), nullable=True)
    
    search_params = Column(JSON, nullable=True)
    cached_results = Column(JSON, nullable=True)
    
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="searches")
    results = relationship("BusinessData", back_populates="search", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_search_location', 'latitude', 'longitude'),
        Index('idx_search_status', 'status', 'user_id'),
        Index('idx_search_params', 'business_type', 'location', 'status')
    )

    def __repr__(self):
        return f"<BusinessSearch {self.business_type} in {self.location}>"

    @property
    def is_complete(self) -> bool:
        return self.status == SearchStatus.COMPLETED

    @property
    def has_error(self) -> bool:
        return self.status == SearchStatus.FAILED

    @property
    def is_active(self) -> bool:
        return self.status in (SearchStatus.QUEUED, SearchStatus.IN_PROGRESS)

    def update_progress(self, progress: float, message: str = None) -> None:
        self.progress = min(max(progress, 0.0), 100.0)
        self.last_updated = datetime.utcnow().isoformat()
        if message:
            self.search_params = {
                **(self.search_params or {}),
                "last_message": message
            }

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            "is_complete": self.is_complete,
            "has_error": self.has_error,
            "is_active": self.is_active,
        })
        return data