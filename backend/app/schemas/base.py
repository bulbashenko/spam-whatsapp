from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda dt: dt.isoformat()
        }
    )


class TimestampedSchema(BaseSchema):
    created_at: datetime
    updated_at: datetime


class IDSchema(BaseSchema):
    id: str


class ResponseSchema(TimestampedSchema, IDSchema):
    pass


class PaginationParams(BaseSchema):
    page: Optional[int] = 1
    per_page: Optional[int] = 10
    
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def limit(self) -> int:
        return self.per_page


class PaginatedResponse(BaseSchema):
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool
    items: list

    @classmethod
    def create(cls, items: list, total: int, params: PaginationParams):
        total_pages = (total + params.per_page - 1) // params.per_page
        return cls(
            total=total,
            page=params.page,
            per_page=params.per_page,
            total_pages=total_pages,
            has_next=params.page < total_pages,
            has_prev=params.page > 1,
            items=items
        )