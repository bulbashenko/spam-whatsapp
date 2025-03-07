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
from app import schemas
from app.models import Contact
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
    
    # Crear un nuevo contacto
    new_contact = Contact(
        email=contact_data.email,
        name=contact_data.name,
        phone_number=contact_data.phone_number
    )
    
    db.add(new_contact)
    await db.commit()  
    await db.refresh(new_contact)
    
    return new_contact  # Retorna el contacto creado

# Obtener contactos con filtros
@router.get("/contacts/", response_model=List[schemas.Contact])
async def get_contacts(
    db: Session = Depends(get_db),
    name: Optional[str] = None,
    company_tag: Optional[str] = None,
    added_date: Optional[str] = None
):
    query = db.query(models.Contact)
    
    # Filtro por nombre
    if name:
        query = query.filter(models.Contact.name.ilike(f"%{name}%"))
    
    # Filtro por etiqueta de la empresa
    if company_tag:
        query = query.filter(models.Contact.company_tag.ilike(f"%{company_tag}%"))
    
    # Filtro por fecha de adición
    if added_date:
        query = query.filter(models.Contact.added_date >= added_date)
    
    contacts = query.all()
    return contacts

# Obtener un contacto por ID
@router.get("/contacts/{contact_id}", response_model=schemas.Contact)
async def get_contact(contact_id: int, db: Session = Depends(get_db)):
    db_contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if db_contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return db_contact

# Eliminar todos los contactos
@router.delete("/contacts/clear")
async def clear_contacts(db: Session = Depends(get_db)):
    db.query(models.Contact).delete()
    db.commit()
    return {"message": "All contacts deleted!"}

# Agregar el router a la aplicación principal
app.include_router(router)
