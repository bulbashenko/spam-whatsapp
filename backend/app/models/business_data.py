from sqlalchemy import Column, String, Float, ForeignKey, JSON, Index, CheckConstraint
from sqlalchemy.orm import relationship
from .base import BaseModel

class BusinessData(BaseModel):
    __tablename__ = "business_data"

    place_id = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False, index=True)
    formatted_address = Column(String(512), nullable=False)
    
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    
    formatted_phone_number = Column(String(50), nullable=True)
    international_phone_number = Column(String(50), nullable=True)
    website = Column(String(512), nullable=True)
    url = Column(String(512), nullable=True)
    
    weekday_text = Column(JSON, nullable=True)
    reviews = Column(JSON, nullable=True)
    rating = Column(Float, CheckConstraint('rating >= 0 AND rating <= 5'), nullable=True)
    user_ratings_total = Column(Float, CheckConstraint('user_ratings_total >= 0'), nullable=True)
    price_level = Column(Float, CheckConstraint('price_level >= 0 AND price_level <= 4'), nullable=True)
    business_status = Column(String(50), nullable=True)
    
    search_text = Column(String, nullable=False, index=True)
    category = Column(String(100), nullable=True, index=True)
    
    types = Column(JSON, nullable=False)
    opening_hours = Column(JSON, nullable=True)
    photos = Column(JSON, nullable=True)
    
    raw_data = Column(JSON, nullable=True)
    
    search_id = Column(String(36), ForeignKey("business_searches.id"), nullable=False)
    search = relationship("BusinessSearch", back_populates="results")

    __table_args__ = (
        Index('idx_location', 'latitude', 'longitude'),
        Index('idx_search_category', 'category', 'search_text'),
        CheckConstraint('latitude >= -90 AND latitude <= 90'),
        CheckConstraint('longitude >= -180 AND longitude <= 180')
    )

    def __repr__(self):
        return f"<BusinessData {self.name} ({self.place_id})>"

    @property
    def location_tuple(self) -> tuple[float, float]:
        return (self.latitude, self.longitude)

    async def to_dict(self) -> dict:
        data = await super().to_dict()
        data["location"] = self.location_tuple
        
        # Ensure weekday_text is always a list
        if self.weekday_text is None:
            data["weekday_text"] = []
        
        if self.reviews is None:
            data["reviews"] = []
            
        return data

    def update_search_text(self) -> None:
        search_parts = [
            self.name,
            self.formatted_address,
            self.category or "",
            *([t for t in self.types] if self.types else [])
        ]
        self.search_text = " ".join(filter(None, search_parts)).lower()