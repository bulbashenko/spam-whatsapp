import httpx
from app.models import Contact
from app.core.config import settings  # Assuming settings contains the base API URL

async def create_contact_via_api(name: str, company_tag: str, email: str, phone: str):
    url = "https://moton.agency/api/v1/contacts/contacts/"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "name": name,
        "company_tag": company_tag,
        "email": email,
        "phone": phone
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                # Log success or return the response data
                return response.json()
            else:
                # Handle failed response
                raise Exception(f"Failed to create contact: {response.text}")
        except httpx.RequestError as exc:
            raise Exception(f"An error occurred while making the request: {str(exc)}")

