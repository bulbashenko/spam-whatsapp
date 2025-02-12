import asyncio
from celery import Task
from typing import Dict, Any, List
import logging
from datetime import datetime
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.worker.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models import BusinessSearch, SearchStatus, BusinessData
from app.services.google_places import GooglePlacesService

logger = logging.getLogger(__name__)

class DatabaseTask(Task):
    _db = None
    _loop = None

    def get_loop(self):
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        return self._loop

    async def get_db(self) -> AsyncSessionLocal:
        if self._db is None:
            self._db = AsyncSessionLocal()
        return self._db

    async def cleanup_db(self):
        if self._db is not None:
            try:
                await self._db.close()
            except Exception as e:
                logger.error(f"Error closing database connection: {str(e)}")
            finally:
                self._db = None

    def cleanup(self):
        if self._loop is not None:
            try:
                if not self._loop.is_closed():
                    self._loop.run_until_complete(self.cleanup_db())
                    self._loop.close()
            except Exception as e:
                logger.error(f"Error cleaning up event loop: {str(e)}")
            finally:
                self._loop = None

@celery_app.task(bind=True, base=DatabaseTask, max_retries=3)
def process_business_search(self, search_id: str, user_id: str):
    search = None
    try:
        loop = self.get_loop()
        
        async def _process():
            nonlocal search
            db = await self.get_db()
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
                processed_count = 0
                error_count = 0
                
                async with GooglePlacesService() as places_service:
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
                        
                        # Search phase is 30% of total progress
                        search_progress = (page_count / max_pages) * 30
                        search.update_progress(search_progress, f"Searching page {page_count}... Found {len(all_results)} results")
                        search.results_count = len(all_results)
                        await db.commit()
                        
                        if not next_page_token or page_count >= max_pages:
                            break
                        
                        await asyncio.sleep(2)
                    
                    batch_size = 10
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
                            place_details_tasks = [places_service.get_place_details(pid) for pid in place_ids]
                            place_details_results = await asyncio.gather(*place_details_tasks, return_exceptions=True)
                            
                            for j, details in enumerate(place_details_results):
                                try:
                                    if isinstance(details, Exception):
                                        logger.error(f"Error fetching place details: {str(details)}")
                                        error_count += 1
                                        continue
                                    
                                    if not details or not details.get("result"):
                                        logger.error(f"No details found for place_id: {place_ids[j]}")
                                        error_count += 1
                                        continue
                                    
                                    place_data = places_service.process_place_data(
                                        details["result"],
                                        fallback_id=place_ids[j]
                                    )
                                    
                                    async with db.begin_nested() as nested_trans:
                                        try:
                                            result = await db.execute(
                                                select(BusinessData).where(BusinessData.place_id == place_ids[j])
                                            )
                                            existing_business = result.scalar_one_or_none()
                                            
                                            if existing_business:
                                                for key, value in place_data.items():
                                                    setattr(existing_business, key, value)
                                                existing_business.search_id = search_id
                                                existing_business.update_search_text()
                                                business = existing_business
                                            else:
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
                                                    raw_data=place_data.get("raw_data", {})
                                                )
                                                business.update_search_text()
                                                db.add(business)
                                            
                                            await db.flush()
                                            processed_count += 1
                                            
                                        except Exception as e:
                                            await nested_trans.rollback()
                                            logger.error(f"Error processing place data: {str(e)}")
                                            error_count += 1
                                            continue
                                
                                except Exception as e:
                                    logger.error(f"Error processing place: {str(e)}")
                                    error_count += 1
                                    continue
                            
                            # Processing phase is 70% of total progress
                            processing_progress = 30 + min((i + batch_size) / len(all_results) * 70, 70)
                            search.update_progress(
                                processing_progress, 
                                f"Processing results {min(i + batch_size, len(all_results))} of {len(all_results)}"
                            )
                            await db.commit()
                
                search.status = SearchStatus.COMPLETED if error_count < len(all_results) else SearchStatus.FAILED
                if search.status == SearchStatus.COMPLETED:
                    search.update_progress(100, f"Completed! Found {processed_count} businesses")
                search.results_count = processed_count
                await db.commit()
                
                return {"status": "completed", "results_count": search.results_count}
                
            except Exception as e:
                logger.error(f"Error processing search: {str(e)}")
                search.status = SearchStatus.FAILED
                await db.commit()
                raise
        
        result = loop.run_until_complete(_process())
        loop.run_until_complete(self.cleanup_db())
        return result
            
    except Exception as e:
        logger.error(f"Task error: {str(e)}")
        try:
            if search:
                async def update_failed_status():
                    db = await self.get_db()
                    try:
                        search.status = SearchStatus.FAILED
                        await db.commit()
                    except Exception as inner_e:
                        logger.error(f"Failed to update search status: {str(inner_e)}")
                
                self.get_loop().run_until_complete(update_failed_status())
        except Exception as cleanup_e:
            logger.error(f"Error during cleanup: {str(cleanup_e)}")
        finally:
            self.cleanup()
        self.retry(exc=e, countdown=60)

@celery_app.task(bind=True, base=DatabaseTask)
def cleanup_old_searches(self, days: int = 30):
    try:
        loop = self.get_loop()
        
        async def _cleanup():
            async with AsyncSessionLocal() as db:
                from datetime import datetime, timedelta
                
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
        
        return loop.run_until_complete(_cleanup())
        
    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")
        raise