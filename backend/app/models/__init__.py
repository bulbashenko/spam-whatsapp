"""
Models initialization module.
Import all models here to ensure proper registration and avoid circular dependencies.
"""

from .base import BaseModel
from .user import User, UserRole, UserPermission
from .business_search import BusinessSearch, SearchStatus
from .business_data import BusinessData
from .whatsapp import WhatsAppAccount, WhatsAppAccountStatus, WhatsAppMessage, WhatsAppMessageStatus
from .google_oauth import GoogleOAuth

# This ensures all models are properly registered with SQLAlchemy
__all__ = [
    'BaseModel',
    'User',
    'UserRole',
    'UserPermission',
    'BusinessSearch',
    'SearchStatus',
    'BusinessData',
    'WhatsAppAccount',
    'WhatsAppAccountStatus',
    'WhatsAppMessage',
    'WhatsAppMessageStatus',
    'GoogleOAuth'
]