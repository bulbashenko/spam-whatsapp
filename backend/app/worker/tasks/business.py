import asyncio
from datetime import datetime, timedelta
import logging
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Optional

from app.worker.celery_app import celery_app
from app.worker.base import DatabaseTask
from app.core.database import AsyncSessionLocal
from app.models import BusinessSearch, SearchStatus, BusinessData, GoogleOAuth
from app.services.google_places import GooglePlacesService
from app.services.google_people import GooglePeopleService
from app.core.redis import (
    cache_business_search, get_cached_business_search,
    cache_place_details, get_cached_place_details,
    cache_location_coordinates, get_cached_location_coordinates
)

logger = logging.getLogger(__name__)
async def store_business_results_as_contacts_impl(
    db: AsyncSession,
    user_id: str,
    search_id: str
) -> bool:
    """
    Store business results as contacts in Google Contacts.
    This implementation function is called by both the search task and
    the dedicated contacts saving task.
    """
    try:
        # Check if user has Google OAuth credentials
        result = await db.execute(
            select(GoogleOAuth).where(
                GoogleOAuth.user_id == user_id,
                GoogleOAuth.is_active == True
            )
        )
        oauth = result.scalar_one_or_none()
        
        if not oauth:
            logger.info(f"User {user_id} has not connected Google account, skipping contacts creation")
            return False
        
        # Get business results
        result = await db.execute(
            select(BusinessData).where(BusinessData.search_id == search_id)
        )
        businesses = result.scalars().all()
        
        if not businesses:
            logger.info(f"No businesses found for search {search_id}")
            return False
        
        # Prepare contact data
        contact_data_list = []
        for business in businesses:
            business_dict = await business.to_dict()
            contact_data = GooglePeopleService.business_to_contact(business_dict)
            contact_data_list.append(contact_data)
        
        # Create contacts in Google
        async with GooglePeopleService(oauth_credentials=oauth.to_credentials_dict()) as people_service:
            results = await people_service.batch_create_contacts(contact_data_list)
            logger.info(f"Created {len(results)} contacts in Google Contacts for search {search_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error storing business results as contacts: {str(e)}")
        return False

async def process_place_details(
    places_service: GooglePlacesService,
    place_id: str,
    db: AsyncSession,
    search_id: str
) -> Optional[BusinessData]:
    """Process single place details with caching"""
    try:
        # Check cache first
        cached_details = await get_cached_place_details(place_id)
        if cached_details:
            logger.info(f"Cache hit for place {place_id}")
            place_data = places_service.process_place_data(
                cached_details,
                fallback_id=place_id
            )
        else:
            details = await places_service.get_place_details(place_id)
            if not details or not details.get("result"):
                logger.error(f"No details found for place_id: {place_id}")
                return None
            try:
                logger.info("\n\n\n\n\n\n\n\n DETAILS: \n\n\n\n\n\n\n\n")
                logger.info(details)
            except Exception as e:
                logger.error(f"Error processing place data to social: {str(e)}")
                
            # Cache the results
            await cache_place_details(place_id, details["result"])
            place_data = places_service.process_place_data(
                details["result"],
                fallback_id=place_id
            )
        
        async with db.begin_nested() as nested_trans:
            try:
                result = await db.execute(
                    select(BusinessData).where(BusinessData.place_id == place_id)
                )
                existing_business = result.scalar_one_or_none()
                
                if existing_business:
                    for key, value in place_data.items():
                        setattr(existing_business, key, value)
                    existing_business.search_id = search_id
                    existing_business.update_search_text()
                    business = existing_business
                else:
                    logger.info(f"Place Data: {place_data}")
                    business = BusinessData(
                        search_id=search_id,
                        place_id=place_data["place_id"],
                        name=place_data["name"],
                        formatted_address=place_data["formatted_address"],
                        latitude=place_data["latitude"],
                        longitude=place_data["longitude"],
                        formatted_phone_number=place_data.get("formatted_phone_number"),
                        international_phone_number=place_data.get("international_phone_number"),
                        website=place_data.get("website"),
                        rating=place_data.get("rating"),
                        user_ratings_total=place_data.get("user_ratings_total"),
                        price_level=place_data.get("price_level"),
                        business_status=place_data.get("business_status"),
                        types=place_data.get("types", []),
                        opening_hours=place_data.get("opening_hours", {}),
                        photos=place_data.get("photos", []),
                        weekday_text=place_data.get("weekday_text", []),
                        reviews=place_data.get("reviews", []),
                        url=place_data.get("url"),
                        raw_data=place_data.get("raw_data", {}),
                        social_media=place_data.get("social_media", {})
                    )
                    business.update_search_text()
                    db.add(business)
                
                await db.flush()
                return business
                
            except Exception as e:
                await nested_trans.rollback()
                logger.error(f"Error processing place data: {str(e)}")
                return None
                
    except Exception as e:
        logger.error(f"Error processing place: {str(e)}")
        return None

@celery_app.task(bind=True, base=DatabaseTask, max_retries=3)
def process_business_search(self, search_id: str, user_id: str):
    """Optimized Celery task to process business search"""
    search = None
    
    async def _process():
        """Process business search with caching and parallel processing"""
        nonlocal search
        async with self.db_session() as db:
            try:
                result = await db.execute(
                    select(BusinessSearch).where(BusinessSearch.id == search_id)
                )
                search = result.scalar_one_or_none()
                
                if not search:
                    logger.error(f"Search {search_id} not found")
                    return
                
                search.status = SearchStatus.IN_PROGRESS
                await db.commit()
                
                all_results = []
                async with GooglePlacesService() as places_service:
                    # Check cache first
                    cached_results = await get_cached_business_search(
                        search.business_type,
                        search.location,
                        search.radius
                    )
                    
                    if cached_results:
                        logger.info(f"Cache hit for search {search_id}")
                        all_results = cached_results
                        search.update_progress(30, f"Found {len(all_results)} results in cache")
                    else:
                        next_page_token = None
                        page_count = 0
                        max_pages = 3
                        
                        while True:
                            search_results = await places_service.search_places(
                                query=search.business_type,
                                location=search.location,
                                radius=search.radius,
                                page_token=next_page_token
                            )
                        
                            current_results = search_results.get("results", [])
                            if not current_results:
                                break
                            
                            all_results.extend(current_results)
                            next_page_token = search_results.get("next_page_token")
                            page_count += 1
                            
                            search_progress = (page_count / max_pages) * 30
                            search.update_progress(search_progress, f"Searching page {page_count}... Found {len(all_results)} results")
                            search.results_count = len(all_results)
                            await db.commit()
                            
                            if not next_page_token or page_count >= max_pages:
                                break
                            
                            await asyncio.sleep(2)
                        
                        # Cache the search results
                        await cache_business_search(
                            search.business_type,
                            search.location,
                            search.radius,
                            all_results
                        )
                
                processed_count = 0
                error_count = 0
                
                # Process places in smaller batches to avoid overwhelming the connection pool
                batch_size = 5  # Reduced batch size
                async with GooglePlacesService() as places_service:
                    for i in range(0, len(all_results), batch_size):
                        batch = all_results[i:i + batch_size]
                        place_ids = []
                        
                        for place in batch:
                            place_id = place.get("place_id") or place.get("id") or f"temp_{place.get('reference', datetime.now().timestamp())}"
                            if place_id:
                                place_ids.append(place_id)
                            else:
                                logger.error(f"Missing place_id in search result")
                                error_count += 1
                        
                        if place_ids:
                            # Process places sequentially within batch
                            for pid in place_ids:
                                try:
                                    result = await process_place_details(places_service, pid, db, search_id)
                                    if result:
                                        processed_count += 1
                                    else:
                                        error_count += 1
                                except Exception as e:
                                    logger.error(f"Error processing place {pid}: {str(e)}")
                                    error_count += 1
                        
                        # Update progress
                        processing_progress = 30 + min((i + batch_size) / len(all_results) * 70, 70)
                        search.update_progress(
                            processing_progress, 
                            f"Processing results {min(i + batch_size, len(all_results))} of {len(all_results)}"
                        )
                        await db.commit()
                
                # Determine if search was successful
                successful_search = error_count < len(all_results)
                
                # Don't automatically save to Google Contacts, just mark search as complete
                if successful_search and processed_count > 0:
                    logger.info(f"Search {search_id} completed with {processed_count} results, waiting for user confirmation to save to Google Contacts")
                
                # Update search status
                search.status = SearchStatus.COMPLETED if successful_search else SearchStatus.FAILED
                if search.status == SearchStatus.COMPLETED:
                    search.update_progress(100, f"Completed! Found {processed_count} businesses")
                search.results_count = processed_count
                await db.commit()
                
                return {"status": "completed", "results_count": search.results_count}
                
            except Exception as e:
                logger.error(f"Error processing search: {str(e)}")
                if search:
                    search.status = SearchStatus.FAILED
                    await db.commit()
                raise

    try:
        return self.run_async(_process())
    except Exception as e:
        logger.error(f"Task error: {str(e)}")
        
        # Try to update search status if we have a search object
        if search:
            async def update_failed_status():
                async with self.db_session() as db:
                    try:
                        result = await db.execute(
                            select(BusinessSearch).where(BusinessSearch.id == search_id)
                        )
                        search = result.scalar_one_or_none()
                        if search:
                            search.status = SearchStatus.FAILED
                            await db.commit()
                    except Exception as inner_e:
                        logger.error(f"Failed to update search status: {str(inner_e)}")

            try:
                self.run_async(update_failed_status())
            except Exception as update_e:
                logger.error(f"Error updating failed status: {str(update_e)}")
        
        self.retry(exc=e, countdown=20)

@celery_app.task(bind=True, base=DatabaseTask)
def store_business_results_as_contacts(self, search_id: str, user_id: str):
    """
    Celery task to save business search results to Google Contacts.
    This is called after user confirmation from the frontend.
    """
    async def _save_contacts():
        async with self.db_session() as db:
            try:
                # Use the implementation function to save contacts
                result = await store_business_results_as_contacts_impl(db, user_id, search_id)
                contacts_count = 0
                
                if result:
                    # Get the count of businesses that were saved
                    result = await db.execute(
                        select(func.count()).select_from(BusinessData).where(
                            BusinessData.search_id == search_id
                        )
                    )
                    contacts_count = result.scalar_one_or_none() or 0
                    logger.info(f"Successfully saved {contacts_count} businesses as Google Contacts")
                    
                # Return a dict with only simple types that can be JSON serialized
                return {
                    "success": bool(result),  # Ensure this is a boolean
                    "contacts_count": int(contacts_count),  # Ensure this is an integer
                    "message": f"Created {contacts_count} contacts in Google Contacts for search {search_id}" if result else "No contacts were saved"
                }
            except Exception as e:
                logger.error(f"Error saving contacts to Google: {str(e)}")
                return {
                    "success": False,
                    "error": str(e),
                    "message": "Failed to save contacts to Google"
                }
    
    try:
        # Execute the async function and get the result
        result = self.run_async(_save_contacts())
        
        # Ensure the result is fully JSON serializable
        try:
            import json
            # Test if the result is JSON serializable
            json.dumps(result)
            return result
        except (TypeError, ValueError) as json_err:
            # If serialization fails, return a simplified result
            logger.error(f"Result serialization error: {str(json_err)}")
            return {
                "success": result.get("success", False) if isinstance(result, dict) else False,
                "contacts_count": result.get("contacts_count", 0) if isinstance(result, dict) else 0,
                "message": "Contacts saved successfully but result details could not be serialized"
            }
    except Exception as e:
        logger.error(f"Error in store_business_results_as_contacts: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "message": "Task failed due to an unexpected error"
        }

@celery_app.task(bind=True, base=DatabaseTask)
def cleanup_old_searches(self, days: int = 7):
    """
    Celery task to cleanup old searches
    """
    async def _cleanup():
        async with self.db_session() as db:
            try:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                
                result = await db.execute(
                    select(BusinessSearch).where(BusinessSearch.created_at < cutoff_date)
                )
                old_searches = result.scalars().all()
                
                for search in old_searches:
                    await db.execute(
                        delete(BusinessData).where(BusinessData.search_id == search.id)
                    )
                    db.delete(search)
                
                await db.commit()
                logger.info(f"Cleaned up {len(old_searches)} old searches")
                
            except Exception as e:
                logger.error(f"Error during cleanup: {str(e)}")
                raise

    try:
        return self.run_async(_cleanup())
    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")
        raise