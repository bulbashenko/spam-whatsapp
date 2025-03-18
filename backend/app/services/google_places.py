from typing import Dict, List, Optional, Any
import aiohttp
import asyncio
from datetime import datetime
import logging
from app.core.config import settings
from fastapi import HTTPException
from app.services.socialmedia import SocialMediaService

logger = logging.getLogger(__name__)

class GooglePlacesService:
    def __init__(self):
        self.api_key = settings.GOOGLE_PLACES_API_KEY="REMOVED"
        self.base_url = "https://maps.googleapis.com/maps/api/place"
        self.retry_count = 3
        self.retry_delay = 1
        self._session = None
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                connector=aiohttp.TCPConnector(limit=10, force_close=True)
            )
        return self._session
        
    async def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        params["key"] = self.api_key
        url = f"{self.base_url}/{endpoint}"
        session = await self._ensure_session()
        
        for attempt in range(self.retry_count):
            try:
                async with session.get(url, params=params) as response:
                        try:
                            data = await response.json()
                        except ValueError as e:
                            logger.error(f"JSON parsing error: {str(e)}")
                            if attempt == self.retry_count - 1:
                                raise HTTPException(
                                    status_code=503,
                                    detail="Invalid response from service"
                                )
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
                            continue
                        
                        if response.status == 200:
                            status = data.get("status")
                            
                            logger.info(f"Google Places API error: {status}")
                            logger.info(f"Response data: {data}")
                            
                            if status == "OK":
                                try:
                                    SocialMedia = SocialMediaService().search_social_profiles(data.get("results", {})[0].get("name", ""))
                                    logger.info(f"Social media profiles: {SocialMedia}")
                                    
                                    data["social_media"] = SocialMedia
                                    logger.info(f"Data after adding social media: {data}")
                                except Exception as e:
                                    logger.error(f"Social media error data: {str(e)}")
                                return data
                            elif status == "ZERO_RESULTS":
                                return {"results": []}
                            elif status in ["OVER_QUERY_LIMIT", "REQUEST_DENIED"]:
                                logger.error(f"API quota/permission error: {status}")
                                raise HTTPException(
                                    status_code=429 if status == "OVER_QUERY_LIMIT" else 403,
                                    detail=f"API {status.lower()}"
                                )
                            else:
                                logger.error(f"Google Places API error: {status}")
                                if attempt == self.retry_count - 1:
                                    raise HTTPException(
                                        status_code=400,
                                        detail=f"API error: {status}"
                                    )
                                await asyncio.sleep(self.retry_delay * (attempt + 1))
                                continue
                        
                        if response.status == 429:
                            wait_time = int(response.headers.get("Retry-After", self.retry_delay))
                            await asyncio.sleep(wait_time)
                            continue
                        
                        logger.info(f"Request failed with status code: {response.status}")
                        logger.debug(f"Response data: {data}")
                        
                            
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Request error: {str(e)}")
                if attempt == self.retry_count - 1:
                    raise HTTPException(
                        status_code=503,
                        detail="Service temporarily unavailable"
                    )
                await asyncio.sleep(self.retry_delay * (attempt + 1))
            
        raise HTTPException(
            status_code=503,
            detail="Maximum retry attempts reached"
        )

    async def search_places(
        self,
        query: str,
        location: str,
        radius: int = 5000,
        type: Optional[str] = None,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            search_query = f"{query} in {location}"
            
            params = {
                "query": search_query,
                "radius": radius,
                "language": "en"
            }
            
            if type:
                params["type"] = type
            if page_token:
                params["pagetoken"] = page_token
                
            return await self._make_request("textsearch/json", params)
            
        except Exception as e:
            logger.error(f"Search error: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Failed to perform search"
            )

    async def get_place_details(self, place_id: str) -> Dict[str, Any]:
        params = {
            "place_id": place_id,
            "fields": "name,formatted_address,geometry,type,business_status,"
                     "formatted_phone_number,international_phone_number,website,rating,"
                     "user_ratings_total,price_level,opening_hours,photos,reviews,url"
        }
        
        return await self._make_request("details/json", params)

    async def geocode_address(self, address: str) -> Optional[Dict[str, float]]:
        params = {"address": address}
        
        try:
            data = await self._make_request("geocode/json", params)
            if data.get("results"):
                location = data["results"][0]["geometry"]["location"]
                return {
                    "lat": location["lat"],
                    "lng": location["lng"]
                }
        except Exception as e:
            logger.error(f"Geocoding error: {str(e)}")
            return None

    def process_place_data(self, place_data: Dict[str, Any], fallback_id: str = None) -> Dict[str, Any]:
        place_id = (
            place_data.get("place_id") or 
            place_data.get("id") or 
            place_data.get("reference") or 
            fallback_id
        )
        
        if not place_id:
            logger.error(f"Missing place_id in response: {place_data}")
            raise HTTPException(
                status_code=400,
                detail="Invalid place data: missing place_id"
            )

        geometry = place_data.get("geometry", {})
        location = geometry.get("location", {}) if geometry else {}
        
        processed_data = {
            "place_id": place_id,
            "name": place_data.get("name", "Unknown"),
            "formatted_address": place_data.get("formatted_address", "No address available"),
            "latitude": location.get("lat"),
            "longitude": location.get("lng"),
            "formatted_phone_number": place_data.get("formatted_phone_number"),
            "international_phone_number": place_data.get("international_phone_number"),
            "website": place_data.get("website"),
            "rating": place_data.get("rating"),
            "user_ratings_total": place_data.get("user_ratings_total"),
            "price_level": place_data.get("price_level"),
            "business_status": place_data.get("business_status"),
            "types": place_data.get("types", []),
            "opening_hours": place_data.get("opening_hours", {}),
            "photos": [photo.get("photo_reference") for photo in place_data.get("photos", []) if photo.get("photo_reference")],
            "weekday_text": place_data.get("opening_hours", {}).get("weekday_text", []),
            "reviews": place_data.get("reviews", []),
            "url": place_data.get("url"),
            "raw_data": place_data
        }

        if not location:
            logger.warning(f"Missing location data for place: {place_data.get('name')} ({place_data.get('place_id')})")

        return processed_data

    async def get_location_predictions(self, input_text: str) -> List[Dict[str, str]]:
        params = {
            "input": input_text,
            "types": "(cities)",
            "language": "en"
        }
        
        try:
            data = await self._make_request("autocomplete/json", params)
            predictions = []
            for prediction in data.get("predictions", []):
                main_text = prediction.get("structured_formatting", {}).get("main_text", "")
                secondary_text = prediction.get("structured_formatting", {}).get("secondary_text", "")
                predictions.append({
                    "place_id": prediction.get("place_id"),
                    "description": prediction.get("description"),
                    "main_text": main_text,
                    "secondary_text": secondary_text
                })
                
            return predictions
            
        except Exception as e:
            logger.error(f"Autocomplete error: {str(e)}")
            return []