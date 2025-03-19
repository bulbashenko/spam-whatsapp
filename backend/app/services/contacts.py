from sqlalchemy.orm import Session
from app.models import Contact

def create_contact(db: Session, name: str, company_tag: str, email: str, phone: str):
    db_contact = Contact(name=name, company_tag=company_tag, email=email, phone=phone)
    db.add(db_contact)  # Add the contact to the session
    db.commit()  # Commit the transaction to save the contact in the database
    db.refresh(db_contact)  # Refresh the contact instance to get the latest data (e.g., generated ID)
    return db_contact  # Return the created contact object
