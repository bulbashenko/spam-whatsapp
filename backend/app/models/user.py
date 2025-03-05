from sqlalchemy import Boolean, Column, String, Enum, JSON
from sqlalchemy.orm import relationship
import enum
from typing import List
from .base import BaseModel
from .whatsapp import WhatsAppAccount


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"


class UserPermission(str, enum.Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    SEARCH = "search"
    EXPORT = "export"


class User(BaseModel):
    __tablename__ = "users"

    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    
    role = Column(Enum(UserRole, name="userrole"), default=UserRole.USER, nullable=False)
    permissions = Column(JSON, default=lambda: [UserPermission.READ.value, UserPermission.SEARCH.value])
    is_active = Column(Boolean, default=True, nullable=False)
    
    search_history_limit = Column(String(10), default="50")
    
    searches = relationship(
        "BusinessSearch",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(BusinessSearch.created_at)"
    )
    
    google_oauth = relationship(
        "GoogleOAuth",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False  # One-to-one relationship
    )

    def __repr__(self):
        return f"<User {self.email}>"
    
    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN
    
    @property
    def is_manager(self) -> bool:
        return self.role == UserRole.MANAGER
    
    def has_permission(self, permission: UserPermission) -> bool:
        if self.is_admin:
            return True
        return permission.value in self.permissions
    
    def add_permission(self, permission: UserPermission) -> None:
        if not self.permissions:
            self.permissions = []
        if permission.value not in self.permissions:
            self.permissions.append(permission.value)
    
    def remove_permission(self, permission: UserPermission) -> None:
        if self.permissions and permission.value in self.permissions:
            self.permissions.remove(permission.value)
    
    whatsapp_accounts = relationship(
        "WhatsAppAccount",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(WhatsAppAccount.created_at)"
    )
    
    async def to_dict(self) -> dict:
        data = await super().to_dict()
        data.pop("hashed_password", None)
        data.update({
            "is_admin": self.is_admin,
            "is_manager": self.is_manager,
            "search_count": len(self.searches)
        })
        return data