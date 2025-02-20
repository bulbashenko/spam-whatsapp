from sqlalchemy import Column, String, ForeignKey, Enum, JSON, Text
from sqlalchemy.orm import relationship
import enum
from typing import Optional, List, Dict, Any
from .base import BaseModel


class WhatsAppMessageStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    ERROR = "error"


class WhatsAppAccountStatus(str, enum.Enum):
    INITIALIZED = "initialized"
    PENDING = "pending"
    ACTIVE = "active"
    ERROR = "error"
    BLOCKED = "blocked"


class WhatsAppAccount(BaseModel):
    __tablename__ = "whatsapp_accounts"

    profile_name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(String(500))
    status = Column(
        Enum(WhatsAppAccountStatus, name="whatsappaccountstatus"),
        default=WhatsAppAccountStatus.PENDING,
        nullable=False
    )
    
    # Chrome profile path
    profile_path = Column(String(500))
    # Additional data (last activity, errors, etc.)
    account_metadata = Column(JSON, default=dict)
    
    # User relationship
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="whatsapp_accounts")

    # Messages relationship
    messages = relationship("WhatsAppMessage", back_populates="account")

    def __repr__(self):
        return f"<WhatsAppAccount {self.profile_name}>"
    
    @property
    def is_ready(self) -> bool:
        return self.status == WhatsAppAccountStatus.ACTIVE
    
    def set_error(self, error_message: str) -> None:
        self.status = WhatsAppAccountStatus.ERROR
        if not isinstance(self.account_metadata, dict):
            self.account_metadata = {}
        self.account_metadata["last_error"] = error_message
        self.account_metadata["last_error_at"] = str(self.updated_at)
    
    def set_active(self) -> None:
        self.status = WhatsAppAccountStatus.ACTIVE
        if not isinstance(self.account_metadata, dict):
            self.account_metadata = {}
        self.account_metadata["last_active"] = str(self.updated_at)
    
    async def to_dict(self) -> Dict[str, Any]:
        data = await super().to_dict()
        data.update({
            "is_ready": self.is_ready,
            "last_error": self.account_metadata.get("last_error") if isinstance(self.account_metadata, dict) else None,
            "last_active": self.account_metadata.get("last_active") if isinstance(self.account_metadata, dict) else None
        })
        return data


class WhatsAppMessage(BaseModel):
    __tablename__ = "whatsapp_messages"

    account_id = Column(String(36), ForeignKey("whatsapp_accounts.id"), nullable=False)
    recipient = Column(String(20), nullable=False)
    message_text = Column(Text, nullable=False)
    status = Column(
        Enum(WhatsAppMessageStatus, name="whatsappmessagestatus"),
        default=WhatsAppMessageStatus.PENDING,
        nullable=False
    )
    error_message = Column(String(500))
    message_metadata = Column(JSON, default=dict, nullable=False)

    # Account relationship
    account = relationship("WhatsAppAccount", back_populates="messages")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.message_metadata is None:
            self.message_metadata = {}

    def __repr__(self):
        return f"<WhatsAppMessage {self.id[:8]} to {self.recipient}>"

    async def to_dict(self) -> Dict[str, Any]:
        data = await super().to_dict()
        # Ensure message_metadata is a dictionary
        metadata = self.message_metadata if isinstance(self.message_metadata, dict) else {}
        data.update({
            "account_id": self.account_id,
            "recipient": self.recipient,
            "message_text": self.message_text,
            "status": self.status,
            "error_message": self.error_message,
            "metadata": metadata
        })
        return data