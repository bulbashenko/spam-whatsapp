from typing import Dict, List, Optional, Any, Tuple
import aiohttp
import asyncio
import logging
import json
from datetime import datetime, timedelta
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

class GooglePeopleService:
    """
    Service for interacting directly with Google People API v1
    https://developers.google.com/people/v1/contacts
    """
    
    def __init__(self, oauth_credentials: Dict[str, str]):
        """
        Initialize with OAuth credentials
        
        Args:
            oauth_credentials: Dictionary with access_token, refresh_token, token_expiry, client_id, client_secret
        """
        self.oauth_credentials = oauth_credentials
        self.access_token = oauth_credentials.get("access_token")
        self.refresh_token = oauth_credentials.get("refresh_token")
        self.token_expiry = oauth_credentials.get("token_expiry")
        self.client_id = oauth_credentials.get("client_id")
        self.client_secret = oauth_credentials.get("client_secret")
        
        # Google People API v1 base URL
        self.base_url = "https://people.googleapis.com/v1"
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        # Ensure we have a valid token
        await self._ensure_valid_token()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def _ensure_valid_token(self):
        """Check if token is expired and refresh if needed"""
        if not self.token_expiry:
            return
        
        expiry = datetime.fromisoformat(self.token_expiry)
        if expiry <= datetime.now() + timedelta(minutes=5):
            await self._refresh_token()
    
    async def _refresh_token(self):
        """Refresh the access token using refresh_token"""
        if not self.refresh_token:
            raise ValueError("No refresh token available")
        
        # Check for missing credentials before attempting refresh
        if not self.client_id:
            from app.core.config import settings
            self.client_id = settings.GOOGLE_OAUTH_CLIENT_ID
            logger.info(f"Using client_id from settings: {self.client_id[:10]}...")
            
        if not self.client_secret:
            from app.core.config import settings
            self.client_secret = settings.GOOGLE_OAUTH_CLIENT_SECRET
            logger.info("Using client_secret from settings")
            
        if not self.client_id:
            raise ValueError("Missing client_id for token refresh")
            
        if not self.client_secret:
            raise ValueError("Missing client_secret for token refresh")
        
        refresh_url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token"
        }
        
        logger.info(f"Refreshing token with client_id: {self.client_id[:10]}...")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(refresh_url, data=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(f"Token refresh error: {text}")
                    raise ValueError(f"Failed to refresh token: {text}")
                
                data = await response.json()
                self.access_token = data["access_token"]
                # Update expiry time
                expires_in = data.get("expires_in", 3600)
                self.token_expiry = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
                
                # Return the new credentials for storage
                return {
                    "access_token": self.access_token,
                    "token_expiry": self.token_expiry,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                }
    
    async def _make_authenticated_request(self, method: str, endpoint: str, params: Optional[Dict] = None, 
                                         json_data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make an authenticated request to Google People API
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (relative to base_url)
            params: Query parameters
            json_data: JSON data for request body
            
        Returns:
            Response data as dictionary
        """
        await self._ensure_valid_token()
        
        # For people API endpoints
        url = f"{self.base_url}/{endpoint}"
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            if method.upper() == "GET":
                async with self.session.get(url, params=params, headers=headers) as response:
                    return await self._process_response(response)
            elif method.upper() == "POST":
                async with self.session.post(url, params=params, json=json_data, headers=headers) as response:
                    return await self._process_response(response)
            elif method.upper() == "DELETE":
                async with self.session.delete(url, params=params, headers=headers) as response:
                    return await self._process_response(response)
            elif method.upper() == "PATCH":
                async with self.session.patch(url, params=params, json=json_data, headers=headers) as response:
                    return await self._process_response(response)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
        except Exception as e:
            logger.error(f"Error making request to Google People API: {e}")
            raise
    
    async def _process_response(self, response: aiohttp.ClientResponse) -> Dict[str, Any]:
        """Process API response and handle errors"""
        if response.status in (200, 201, 204):
            if response.status == 204:  # No content
                return {}
            return await response.json()
        
        error_text = await response.text()
        
        # Check for insufficient scope errors
        if response.status == 403 and "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in error_text:
            logger.error(f"Google scope error: {error_text}")
            logger.error("User needs to disconnect and reconnect Google account to get proper permissions")
            raise ValueError("insufficient_google_scopes: Google token has insufficient permissions. Please disconnect and reconnect your account.")
        
        logger.error(f"Google People API error: {response.status} - {error_text}")
        
        if response.status == 401:
            # Token might be expired, try to refresh and retry
            await self._refresh_token()
            raise ValueError("Authentication failed. Token refreshed, please retry the operation.")
        
        raise ValueError(f"Google People API error: {response.status} - {error_text}")
    
    @staticmethod
    def business_to_contact(business_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert business data to Google People API contact format
        
        Args:
            business_data: Dictionary containing business data
            
        Returns:
            Dictionary in Google People API contact format
        """
        # Prepare contact data
        contact_data = {}
        
        # Get basic info
        contact_data["name"] = business_data.get("name", "")
        
        # Get phone numbers
        phone_numbers = []
        
        # First try international format (preferred)
        if business_data.get("international_phone_number"):
            phone = business_data["international_phone_number"].strip()
            if phone:
                phone_numbers.append(phone)
        
        # Then try formatted phone number
        if business_data.get("formatted_phone_number"):
            phone = business_data["formatted_phone_number"].strip()
            if phone and phone not in phone_numbers:
                phone_numbers.append(phone)
        
        # Check for additional phone numbers in raw data
        if business_data.get("raw_data"):
            raw_data = business_data["raw_data"]
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except:
                    raw_data = {}
            
            if isinstance(raw_data, dict):
                # Extract additional phone numbers from raw_data
                for key in ["phone", "phone_number", "secondary_phone", "mobile_phone", "telephone"]:
                    if raw_data.get(key) and isinstance(raw_data[key], str):
                        phone = raw_data[key].strip()
                        if phone and phone not in phone_numbers:
                            phone_numbers.append(phone)
        
        contact_data["phone_numbers"] = phone_numbers
        
        # Get address
        address = None
        if business_data.get("formatted_address"):
            address = business_data["formatted_address"]
        elif business_data.get("vicinity"):
            address = business_data["vicinity"]
            
        if address:
            contact_data["addresses"] = [address]
        
        # Get website
        if business_data.get("website"):
            contact_data["websites"] = [business_data["website"]]
        
        # Get additional information for notes
        notes = []
        
        if business_data.get("categories"):
            categories = business_data["categories"]
            if isinstance(categories, list) and categories:
                notes.append(f"Categories: {', '.join(categories)}")
        
        if business_data.get("rating"):
            rating = business_data["rating"]
            notes.append(f"Rating: {rating}")
            
        if business_data.get("place_id"):
            place_id = business_data["place_id"]
            notes.append(f"Google Place ID: {place_id}")
            
        if phone_numbers:
            notes.append(f"Phone numbers: {', '.join(phone_numbers)}")
            
        contact_data["notes"] = notes
        
        return contact_data
    
    async def create_contact(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a contact in Google Contacts using People API
        https://developers.google.com/people/api/rest/v1/people/createContact
        
        Args:
            contact_data: Dictionary with contact data
            
        Returns:
            Created contact information
        """
        # Convert to Google People API format
        person = {
            "names": [
                {
                    "givenName": contact_data.get("name", ""),
                    "displayName": contact_data.get("name", "")
                }
            ]
        }
        
        # Add phone numbers
        if contact_data.get("phone_numbers"):
            phone_numbers = []
            for phone in contact_data.get("phone_numbers"):
                if phone:
                    phone_numbers.append({
                        "value": phone,
                        "type": "work"
                    })
            if phone_numbers:
                person["phoneNumbers"] = phone_numbers
        
        # Add addresses
        if contact_data.get("addresses"):
            addresses = []
            for address in contact_data.get("addresses"):
                if address:
                    addresses.append({
                        "formattedValue": address,
                        "type": "work"
                    })
            if addresses:
                person["addresses"] = addresses
        
        # Add websites
        if contact_data.get("websites"):
            urls = []
            for website in contact_data.get("websites"):
                if website:
                    urls.append({
                        "value": website,
                        "type": "work"
                    })
            if urls:
                person["urls"] = urls
        
        # Add notes
        if contact_data.get("notes"):
            notes = contact_data.get("notes", [])
            if notes:
                person["biographies"] = [
                    {
                        "value": "\n".join(notes),
                        "contentType": "TEXT_PLAIN"
                    }
                ]
        
        # Call Google People API directly to create the contact
        endpoint = "people:createContact"
        return await self._make_authenticated_request("POST", endpoint, json_data=person)
    
    async def batch_create_contacts(self, contact_data_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create multiple contacts in Google Contacts using the batch API endpoint
        
        Args:
            contact_data_list: List of contact data dictionaries
            
        Returns:
            List of created contacts
        """
        if not contact_data_list:
            return []
        
        # Ensure token is valid before batch processing
        try:
            await self._ensure_valid_token()
        except Exception as e:
            logger.error(f"Failed to refresh token before batch processing: {e}")
            return []
        
        total_contacts = len(contact_data_list)
        logger.info(f"Starting batch creation of {total_contacts} contacts using batch API")
        
        # Convert contact data to Google People API format
        contacts = []
        for contact_data in contact_data_list:
            person = {"contactPerson": self._format_contact_for_api(contact_data)}
            contacts.append(person)
        
        # Prepare batch request payload
        batch_payload = {"contacts": contacts}
        
        # Call batch API endpoint
        try:
            # Using batch API endpoint: people:batchCreateContacts
            endpoint = "people:batchCreateContacts"
            params = {"readMask": "names,phoneNumbers,emailAddresses,addresses,urls,biographies"}
            
            response = await self._make_authenticated_request(
                method="POST",
                endpoint=endpoint,
                params=params,
                json_data=batch_payload
            )
            
            # Process and return results
            created_people = response.get("createdPeople", [])
            logger.info(f"Successfully created {len(created_people)} contacts in one batch operation")
            return created_people
            
        except ValueError as e:
            if "Authentication failed" in str(e):
                try:
                    logger.info("Authentication failed, refreshing token and retrying batch")
                    await self._refresh_token()
                    
                    # Retry the batch request
                    endpoint = "people:batchCreateContacts"
                    params = {"readMask": "names,phoneNumbers,emailAddresses,addresses,urls,biographies"}
                    
                    response = await self._make_authenticated_request(
                        method="POST",
                        endpoint=endpoint,
                        params=params,
                        json_data=batch_payload
                    )
                    
                    created_people = response.get("createdPeople", [])
                    logger.info(f"Successfully created {len(created_people)} contacts after token refresh")
                    return created_people
                    
                except Exception as refresh_e:
                    logger.error(f"Failed to refresh token for batch operation: {refresh_e}")
                    return []
            else:
                logger.error(f"Error in batch contact creation: {e}")
                return []
        except ValueError as e:
            error_str = str(e)
            # If this is already our special insufficient scopes error, re-raise it
            if "insufficient_google_scopes:" in error_str:
                # This will be caught by the frontend and display appropriate message
                logger.error("Insufficient Google scopes for batch contact creation")
                raise
            elif "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in error_str:
                # Format a more user-friendly error and raise
                logger.error("Google token has insufficient permissions to create contacts")
                raise ValueError("insufficient_google_scopes: User needs to disconnect and reconnect their Google account to get full contact permissions")
            else:
                logger.error(f"Error in batch contact creation: {error_str}")
                return []
        except Exception as e:
            error_str = str(e)
            if "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in error_str:
                logger.error("Google token has insufficient permissions to create contacts")
                raise ValueError("insufficient_google_scopes: User needs to disconnect and reconnect their Google account to get full contact permissions")
            else:
                logger.error(f"Error in batch contact creation: {error_str}")
                return []
    
    def _format_contact_for_api(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format a contact for the Google People API
        
        Args:
            contact_data: Dictionary with contact data from business_to_contact
            
        Returns:
            Properly formatted person object for the API
        """
        person = {
            "names": [
                {
                    "givenName": contact_data.get("name", ""),
                    "displayName": contact_data.get("name", "")
                }
            ]
        }
        
        # Add phone numbers
        if contact_data.get("phone_numbers"):
            phone_numbers = []
            for phone in contact_data.get("phone_numbers"):
                if phone:
                    phone_numbers.append({
                        "value": phone,
                        "type": "work"
                    })
            if phone_numbers:
                person["phoneNumbers"] = phone_numbers
        
        # Add addresses
        if contact_data.get("addresses"):
            addresses = []
            for address in contact_data.get("addresses"):
                if address:
                    addresses.append({
                        "formattedValue": address,
                        "type": "work"
                    })
            if addresses:
                person["addresses"] = addresses
        
        # Add websites
        if contact_data.get("websites"):
            urls = []
            for website in contact_data.get("websites"):
                if website:
                    urls.append({
                        "value": website,
                        "type": "work"
                    })
            if urls:
                person["urls"] = urls
        
        # Add notes
        if contact_data.get("notes"):
            notes = contact_data.get("notes", [])
            if notes:
                person["biographies"] = [
                    {
                        "value": "\n".join(notes),
                        "contentType": "TEXT_PLAIN"
                    }
                ]
                
        return person
    
    async def search_contacts(self, query: str) -> Dict[str, Any]:
        """
        Search for contacts in Google Contacts
        https://developers.google.com/people/api/rest/v1/people.connections/search
        
        Args:
            query: Search query
            
        Returns:
            Search results
        """
        endpoint = "people:searchContacts"
        params = {
            "query": query,
            "readMask": "names,phoneNumbers,emailAddresses,addresses,urls"
        }
        return await self._make_authenticated_request("GET", endpoint, params=params)
    
    @staticmethod
    def generate_oauth_url(client_id: str, redirect_uri: str, state: str = None) -> str:
        """
        Generate OAuth URL for Google People API authorization
        
        Args:
            client_id: Google OAuth client ID
            redirect_uri: Redirect URI after authorization
            state: Optional state parameter for security
            
        Returns:
            Authorization URL
        """
        auth_url = "https://accounts.google.com/o/oauth2/auth"
        
        # Use full contacts scope to enable write operations (creating contacts)
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/contacts",  # Full scope with write permissions
            "access_type": "offline",
            "prompt": "consent",  # Force to get refresh token
            "include_granted_scopes": "true"  # Include any previously granted scopes
        }
        
        if state:
            params["state"] = state
            
        return f"{auth_url}?{urlencode(params)}"
    
    @staticmethod
    async def exchange_code_for_tokens(code: str, client_id: str, client_secret: str, 
                                     redirect_uri: str) -> Dict[str, str]:
        """
        Exchange authorization code for tokens
        
        Args:
            code: Authorization code from OAuth callback
            client_id: Google OAuth client ID
            client_secret: Google OAuth client secret
            redirect_uri: Redirect URI used in authorization
            
        Returns:
            Dictionary with access_token, refresh_token, and token_expiry
        """
        token_url = "https://oauth2.googleapis.com/token"
        
        payload = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, data=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    raise ValueError(f"Failed to exchange code for tokens: {text}")
                
                data = await response.json()
                
                # Calculate token expiry
                expires_in = data.get("expires_in", 3600)
                token_expiry = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
                
                return {
                    "access_token": data["access_token"],
                    "refresh_token": data.get("refresh_token", ""),
                    "token_expiry": token_expiry
                }