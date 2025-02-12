from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
from .base import ResponseSchema
from app.models.user import UserRole


class UserBase(BaseModel):
    email: EmailStr
    role: Optional[UserRole] = UserRole.USER
    is_active: Optional[bool] = True
    search_history_limit: Optional[str] = "50"


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    password_confirm: str = Field(..., min_length=8)

    @validator('password_confirm')
    def passwords_match(cls, v, values):
        if 'password' in values and v != values['password']:
            raise ValueError('Passwords do not match')
        return v


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8)
    is_active: Optional[bool] = None
    search_history_limit: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(ResponseSchema, UserBase):
    class Config:
        json_schema_extra = {
            "example": {
                "id": "d0093878-eb31-49a4-8174-5908fe4648f6",
                "email": "john@example.com",
                "role": "user",
                "is_active": True,
                "search_history_limit": "50",
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00"
            }
        }


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    email: str
    user_id: str
    role: UserRole