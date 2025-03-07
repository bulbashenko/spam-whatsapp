# models.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Contact(Base):
    __tablename__ = 'contacts'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    company_tag = Column(String, index=True)
    added_date = Column(DateTime, default=datetime.utcnow)
    email = Column(String, index=True)
    phone = Column(String, index=True)
