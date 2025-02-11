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

    async def get_db(self) -> AsyncSessionLocal:
        if self._db is None:
            self._db = AsyncSessionLocal()
        return self._db

    async def cleanup_db(self):
        if self._db is not None:
            await self._db.close()
            self._db = None

@celery_app.task(bind=True, base=DatabaseTask, max_retries=3)
def process_business_search(self, search_id: str, user_id: str):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def _process():
            db = await self.get_db()
            result = await db.execute(
                select(BusinessSearch).where(BusinessSearch.id == search_id)
            )
            search = result.scalar_one_or_none()
            
            if not search:
                logger.error(f"Search {search_id} not found")
                return
            
            search.status = SearchStatus.IN_PROGRESS
            await db.commit()
            
            places_service = GooglePlacesService()
            
            all_results = []
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
                
                search.progress = (page_count / max_pages) * 100
                search.results_count = len(all_results)
                await db.commit()
                
                if not next_page_token or page_count >= max_pages:
                    break
                
                await asyncio.sleep(2)
                
                retry_count = 3
                retry_delay = 2
                success = False
                
                for attempt in range(retry_count):
                    try:
                        if attempt > 0:
                            await asyncio.sleep(retry_delay * attempt)
                        
                        next_results = await places_service.search_places(
                            query=search.business_type,
                            location=search.location,
                            radius=search.radius,
                            page_token=next_page_token
                        )
                        
                        if next_results.get("status") == "OK":
                            search_results = next_results
                            success = True
                            break
                            
                    except Exception as e:
                        logger.error(f"Error getting next page (attempt {attempt + 1}): {str(e)}")
                        continue
                
                if not success:
                    logger.warning("Failed to get next page after all retries")
                    break
            
            try:
                search.results_count = len(all_results)
                
                processed_count = 0
                error_count = 0
                
                for i, place in enumerate(all_results):
                    try:
                        place_id = place.get("place_id") or place.get("id") or f"temp_{place.get('reference', datetime.now().timestamp())}"
                        if not place_id:
                            logger.error(f"Missing place_id in search result")
                            error_count += 1
                            continue
                            
                        place_details = await places_service.get_place_details(place_id)
                        
                        if not place_details or not place_details.get("result"):
                            logger.error(f"No details found for place_id: {place_id}")
                            error_count += 1
                            continue
                        
                        place_data = places_service.process_place_data(
                            place_details["result"],
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
                                search.progress = (i + 1) / len(all_results) * 100
                                await db.commit()
                            except Exception as e:
                                await nested_trans.rollback()
                                logger.error(f"Error processing place data: {str(e)}")
                                error_count += 1
                                continue
                        
                        await db.commit()
                    except Exception as e:
                        logger.error(f"Error processing place: {str(e)}")
                        error_count += 1
                        continue
                
                search.status = SearchStatus.COMPLETED if error_count < len(all_results) else SearchStatus.FAILED
                search.results_count = processed_count
                await db.commit()
            except Exception as e:
                logger.error(f"Error processing search: {str(e)}")
                search.status = SearchStatus.FAILED
                await db.commit()
                raise
            
            return {"status": "completed", "results_count": search.results_count}
        
        result = loop.run_until_complete(_process())
        loop.run_until_complete(self.cleanup_db())
        return result
            
    except Exception as e:
        logger.error(f"Task error: {str(e)}")
        loop.run_until_complete(self.cleanup_db())
        self.retry(exc=e, countdown=60)

@celery_app.task(bind=True)
def cleanup_old_searches(self, days: int = 30):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
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