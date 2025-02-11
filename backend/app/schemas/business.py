from pydantic import BaseModel, Field, validator, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime
from .base import ResponseSchema, PaginatedResponse
from app.models.business_search import SearchStatus


class BusinessSearchCreate(BaseModel):
    business_type: str = Field(..., min_length=2, max_length=100)
    location: str = Field(..., min_length=2, max_length=100)
    radius: Optional[int] = Field(5000, ge=1, le=50000)
    search_params: Optional[Dict[str, Any]] = None

    @validator('radius')
    def validate_radius(cls, v):
        if v > 50000:
            raise ValueError('Radius cannot exceed 50000 meters (50km)')
        return v


class BusinessSearchUpdate(BaseModel):
    status: Optional[SearchStatus] = None
    results_count: Optional[int] = None
    error_message: Optional[str] = None


class BusinessSearchResponse(ResponseSchema):
    business_type: str
    location: str
    radius: int
    status: SearchStatus
    results_count: int
    error_message: Optional[str]
    search_params: Optional[Dict[str, Any]]
    user_id: str


class BusinessDataBase(BaseModel):
    place_id: str
    name: str
    formatted_address: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    formatted_phone_number: Optional[str] = None
    international_phone_number: Optional[str] = None
    website: Optional[HttpUrl] = None
    rating: Optional[float] = Field(None, ge=0, le=5)
    user_ratings_total: Optional[int] = None
    price_level: Optional[int] = Field(None, ge=0, le=4)
    business_status: Optional[str] = None
    types: List[str]
    opening_hours: Optional[Dict[str, Any]] = None
    photos: Optional[List[str]] = None


class BusinessDataResponse(ResponseSchema, BusinessDataBase):
    search_id: str

    class Config:
        json_schema_extra = {
            "example": {
                "id": "d0093878-eb31-49a4-8174-5908fe4648f6",
                "place_id": "ChIJ...",
                "name": "Business Name",
                "formatted_address": "123 Main St, City, Country",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "rating": 4.5,
                "types": ["restaurant", "food"],
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00"
            }
        }


class BusinessSearchResults(PaginatedResponse):
    items: List[BusinessDataResponse]




class BusinessSearchStats(BaseModel):
    """Schema for business search statistics."""
    total_searches: int
    completed_searches: int
    failed_searches: int
    average_results: float
    most_searched_types: List[Dict[str, Any]]
    most_searched_locations: List[Dict[str, Any]]
    last_search: Optional[datetime]


class BusinessDetailsResponse(ResponseSchema, BusinessDataBase):
    """Schema for detailed business information."""
    formatted_phone_number: Optional[str]
    international_phone_number: Optional[str]
    weekday_text: Optional[List[str]]
    reviews: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="List of reviews with author, rating, and text"
    )
    url: Optional[HttpUrl] = Field(
        None,
        description="Google Maps URL"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "d0093878-eb31-49a4-8174-5908fe4648f6",
                "place_id": "ChIJ...",
                "name": "Business Name",
                "formatted_address": "123 Main St, City, Country",
                "formatted_phone_number": "+1 234-567-8900",
                "international_phone_number": "+12345678900",
                "website": "https://example.com",
                "rating": 4.5,
                "reviews": [
                    {
                        "author_name": "John Doe",
                        "rating": 5,
                        "text": "Great place!",
                        "time": "2024-01-01T00:00:00"
                    }
                ],
                "weekday_text": [
                    "Monday: 9:00 AM – 10:00 PM",
                    "Tuesday: 9:00 AM – 10:00 PM"
                ],
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00"
            }
        }