from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Contact

async def create_contact(db: AsyncSession, name: str, company_tag: str, email: str, phone: str):
    db_contact = Contact(name=name, company_tag=company_tag, email=email, phone=phone)
    db.add(db_contact)
    await db.commit()  # Commit the transaction asynchronously
    await db.refresh(db_contact)  # Refresh the contact instance asynchronously
    return db_contact
