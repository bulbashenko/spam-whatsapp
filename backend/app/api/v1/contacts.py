from fastapi import FastAPI, Depends, HTTPException, Query, APIRouter
from sqlalchemy.orm import Session
from typing import List, Optional
import app.models as models
import app.schemas.contacts as schemas
from app.core.database import get_db
from app.models import Contact
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.database import get_db_session

app = FastAPI()

router = APIRouter(prefix="/contacts", tags=["Contacts"])

@router.post("/contacts/", response_model=schemas.Contact, status_code=status.HTTP_201_CREATED)
async def create_contact(
    contact_data: schemas.ContactCreate,
    db: AsyncSession = Depends(get_db_session)
):
    stmt = select(Contact).where(Contact.email == contact_data.email)
    result = await db.execute(stmt)
    existing_contact = result.scalar_one_or_none()
    if existing_contact:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact with this email already exists"
        )
    
    new_contact = Contact(
        email=contact_data.email,
        name=contact_data.name,
        phone_number=contact_data.phone_number
    )
    
    db.add(new_contact)
    await db.commit()  
    await db.refresh(new_contact)
    
    return new_contact

@router.get("/contacts/", response_model=List[schemas.Contact])
async def get_contacts(
    db: AsyncSession = Depends(get_db_session),
    name: Optional[str] = None,
    company_tag: Optional[str] = None,
    added_date: Optional[str] = None
):
    stmt = select(models.Contact)
    
    if name:
        stmt = stmt.where(models.Contact.name.ilike(f"%{name}%"))
    
    if company_tag:
        stmt = stmt.where(models.Contact.company_tag.ilike(f"%{company_tag}%"))
    
    if added_date:
        stmt = stmt.where(models.Contact.added_date >= added_date)
    
    result = await db.execute(stmt)
    contacts = result.scalars().all()
    return contacts

@router.get("/contacts/{contact_id}", response_model=schemas.Contact)
async def get_contact(contact_id: int, db: Session = Depends(get_db)):
    db_contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if db_contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return db_contact

@router.delete("/contacts/clear")
async def clear_contacts(db: Session = Depends(get_db)):
    db.query(models.Contact).delete()
    db.commit()
    return {"message": "All contacts deleted!"}

app.include_router(router)
