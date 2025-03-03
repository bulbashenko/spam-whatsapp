from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict
from datetime import datetime
from .base import ResponseSchema
from app.models.whatsapp import WhatsAppAccountStatus, WhatsAppMessageStatus


class WhatsAppAccountBase(BaseModel):
    profile_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)


class WhatsAppAccountCreate(WhatsAppAccountBase):
    pass


class WhatsAppAccountUpdate(BaseModel):
    profile_name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    status: Optional[WhatsAppAccountStatus] = None


class WhatsAppAccountResponse(ResponseSchema, WhatsAppAccountBase):
    status: WhatsAppAccountStatus
    is_ready: bool
    last_error: Optional[str] = None
    last_active: Optional[str] = None
    user_id: str

    @validator('status', pre=True)
    def normalize_status(cls, v):
        if isinstance(v, str):
            return v.lower()
        if hasattr(v, 'value'):
            return v.value
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "id": "d0093878-eb31-49a4-8174-5908fe4648f6",
                "profile_name": "main_account",
                "description": "Main WhatsApp account",
                "status": "active",
                "is_ready": True,
                "last_active": "2024-01-01T00:00:00",
                "user_id": "user123",
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00"
            }
        }


class WhatsAppMessageRecipient(BaseModel):
    phone: str = Field(..., pattern=r'^\+[1-9]\d{1,14}$')
    message: str = Field(..., min_length=1)


class WhatsAppMessageBulk(BaseModel):
    account_id: str
    recipients: List[WhatsAppMessageRecipient]
    wait_time: Optional[int] = Field(60, ge=30, le=300)


class WhatsAppMessageHistory(ResponseSchema):
    account_id: str
    recipient: str
    message_text: str
    status: WhatsAppMessageStatus
    error_message: Optional[str] = None
    metadata: Dict = Field(default_factory=dict)

    @validator('status', pre=True)
    def normalize_status(cls, v):
        if isinstance(v, str):
            return v.lower()
        if hasattr(v, 'value'):
            return v.value
        return v

    @validator('metadata', pre=True)
    def ensure_dict(cls, v):
        if v is None:
            return {}
        if isinstance(v, dict):
            return v
        try:
            # Try to convert to dict if possible
            return dict(v)
        except (TypeError, ValueError):
            return {}

    class Config:
        json_schema_extra = {
            "example": {
                "id": "8d559010-ba14-4fc5-bbcd-e0c4bd7f3b18",
                "account_id": "f99f35a7-7a4d-49cf-8b70-1f4c0109a9fa",
                "recipient": "+15551873951",
                "message_text": "Hello!",
                "status": "sent",
                "error_message": None,
                "metadata": {
                    "sent_at": "2025-02-19T23:12:08.484586"
                },
                "created_at": "2025-02-19T23:12:08.484586",
                "updated_at": "2025-02-19T23:12:08.484586"
            }
        }


class WhatsAppMessageResponse(BaseModel):
    success: bool
    account_id: str
    recipient: str
    message_id: Optional[str] = None
    error: Optional[str] = None
    timestamp: datetime


class WhatsAppSessionInit(BaseModel):
    wait_time: Optional[int] = Field(60, ge=30, le=300)


class WhatsAppQRCodeResponse(BaseModel):
    """Response schema with QR code and account metadata"""
    account_id: str
    qr_code: Optional[str] = None
    status: WhatsAppAccountStatus
    error: Optional[str] = None
    status_message: Optional[str] = None
    metadata: Optional[Dict] = None
    authenticated: bool = False  # Добавленное поле - флаг аутентификации
    close_modal: bool = False    # Добавленное поле - флаг закрытия модального окна

    @validator('status', pre=True)
    def normalize_status(cls, v):
        if isinstance(v, str):
            return v.lower()
        if hasattr(v, 'value'):
            return v.value
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "account_id": "d0093878-eb31-49a4-8174-5908fe4648f6",
                "qr_code": "base64_encoded_qr_code",
                "status": "pending",
                "error": None,
                "status_message": "Waiting for QR code scan...",
                "metadata": {
                    "last_active": "2024-01-01T00:00:00",
                    "chats_count": 100,
                    "last_sync": "2024-01-01T00:00:00",
                    "last_error": None,
                    "last_error_at": None
                },
                "authenticated": False,
                "close_modal": False
            }
        }

class WhatsAppSessionResponse(BaseModel):
    success: bool
    account_id: str
    status: WhatsAppAccountStatus
    error: Optional[str] = None
    qr_code: Optional[str] = None  # Base64 QR code if scanning is required

    @validator('status', pre=True)
    def normalize_status(cls, v):
        if isinstance(v, str):
            return v.lower()
        if hasattr(v, 'value'):
            return v.value
        return v