from sqlalchemy import Column, String, JSON, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Optional, Dict, Any
from .base import BaseModel


class GoogleOAuth(BaseModel):
    """Model for storing Google OAuth credentials."""
    __tablename__ = "google_oauth_credentials"

    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    user = relationship("User", back_populates="google_oauth")
    
    access_token = Column(String(2048), nullable=True)
    refresh_token = Column(String(2048), nullable=True)
    token_type = Column(String(50), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    
    scopes = Column(JSON, nullable=True)
    account_email = Column(String(255), nullable=True)
    
    is_active = Column(Boolean, default=True, nullable=False)
    
    def __repr__(self):
        return f"<GoogleOAuth for user {self.user_id}>"
    
    @property
    def is_token_valid(self) -> bool:
        """Check if the access token is still valid."""
        if not self.expires_at:
            return False
        # Add 5 minute buffer
        return datetime.utcnow() < self.expires_at
    
    def to_credentials_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for GooglePeopleService."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }
    
    async def to_dict(self) -> dict:
        """Convert to dictionary format for API responses."""
        data = await super().to_dict()
        # Don't expose tokens in API responses
        data.pop("access_token", None)
        data.pop("refresh_token", None)
        
        data.update({
            "is_valid": self.is_token_valid,
            "connected_email": self.account_email
        })
        return data