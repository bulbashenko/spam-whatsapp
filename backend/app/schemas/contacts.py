# schemas.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ContactBase(BaseModel):
    name: str
    company_tag: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

class ContactCreate(ContactBase):
    pass

class Contact(ContactBase):
    id: int
    added_date: datetime

    class Config:
        orm_mode = True
