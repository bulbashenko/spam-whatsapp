from sqlalchemy.ext.asyncio import AsyncSession
from models.contacts import Contact
from app.core.database import get_db

async def create_contact_via_api(name: str, company_tag: str, email: str, phone: str):
    async with get_db() as session:
        new_contact = Contact(
            name=name,
            company_tag=company_tag,
            email=email,
            phone=phone
        )
        session.add(new_contact)
        await session.commit()
        await session.refresh(new_contact)
        return new_contact
