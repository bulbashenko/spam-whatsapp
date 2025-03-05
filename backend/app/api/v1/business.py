from fastapi import APIRouter, Depends, HTTPException, status, Response, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from celery.result import AsyncResult

logger = logging.getLogger(__name__)
from app.core.database import get_db_session
from app.core.security import get_current_user
from app.models.user import User
from app.models.business_search import BusinessSearch, SearchStatus
from app.models.business_data import BusinessData
from app.services.export import ExportService
from app.services.google_places import GooglePlacesService
from app.schemas.business import (
    BusinessSearchCreate,
    BusinessSearchResponse,
    BusinessDataResponse,
    BusinessSearchResults,
    BusinessSearchStats,
    BusinessDetailsResponse
)
from app.worker.tasks import process_business_search, store_business_results_as_contacts
from app.schemas.base import PaginationParams

router = APIRouter(prefix="/business", tags=["business"])

@router.get("/locations/predict")
async def predict_locations(query: str):
    async with GooglePlacesService() as places_service:
        predictions = await places_service.get_location_predictions(query)
        return {"predictions": predictions}

@router.post("/search/save-to-google/{search_id}")
async def save_search_to_google_contacts(
    search_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Save search results to Google Contacts after user confirmation
    
    Args:
        search_id: ID of the search to save
        background_tasks: FastAPI background tasks
        current_user: Currently authenticated user
        db: Database session
    
    Returns:
        Task information for tracking the operation
    """
    # Verify the search exists and belongs to the user
    result = await db.execute(
        select(BusinessSearch).where(
            BusinessSearch.id == search_id,
            BusinessSearch.user_id == current_user.id
        )
    )
    search = result.scalar_one_or_none()
    
    if not search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Search not found"
        )
    
    # Verify the search is completed
    if search.status != SearchStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search is not completed yet"
        )
    
    # Get the count of businesses for the user's information
    count_result = await db.execute(
        select(func.count()).select_from(BusinessData).where(
            BusinessData.search_id == search_id
        )
    )
    businesses_count = count_result.scalar_one()
    
    # Create a background task to save to Google Contacts
    task = store_business_results_as_contacts.delay(
        search_id=search_id,
        user_id=current_user.id
    )
    
    return {
        "task_id": task.id,
        "status": "started",
        "message": f"Saving {businesses_count} businesses to Google Contacts",
        "count": businesses_count
    }

@router.get("/search/task/{task_id}")
async def get_google_contacts_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get the status of a Google Contacts save task
    
    Args:
        task_id: ID of the task to check
        current_user: Currently authenticated user
    
    Returns:
        Task status information
    """
    task_result = AsyncResult(task_id)
    
    response = {
        "task_id": task_id,
        "status": task_result.status,
        "done": task_result.ready()
    }
    
    if task_result.ready():
        if task_result.successful():
            response["result"] = task_result.get()
        else:
            response["error"] = str(task_result.result)
    
    return response

@router.post("/search", response_model=BusinessSearchResponse)
async def create_search(
    search_data: BusinessSearchCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    search = BusinessSearch(
        business_type=search_data.business_type,
        location=search_data.location,
        radius=search_data.radius,
        search_params=search_data.search_params,
        user_id=current_user.id,
        status=SearchStatus.PENDING
    )
    
    db.add(search)
    await db.commit()
    await db.refresh(search)
    
    process_business_search.delay(search.id, current_user.id)
    
    return search

@router.get("/search/{search_id}", response_model=BusinessSearchResponse)
async def get_search(
    search_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(
        select(BusinessSearch).where(
            BusinessSearch.id == search_id,
            BusinessSearch.user_id == current_user.id
        )
    )
    search = result.scalar_one_or_none()
    
    if not search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Search not found"
        )
    
    return search

@router.get("/search/{search_id}/results", response_model=BusinessSearchResults)
async def get_search_results(
    search_id: str,
    params: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(
        select(BusinessSearch).where(
            BusinessSearch.id == search_id,
            BusinessSearch.user_id == current_user.id
        )
    )
    search = result.scalar_one_or_none()
    
    if not search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Search not found"
        )
    
    count_result = await db.execute(
        select(func.count()).select_from(BusinessData).where(
            BusinessData.search_id == search_id
        )
    )
    total = count_result.scalar_one()
    
    result = await db.execute(
        select(BusinessData)
        .where(BusinessData.search_id == search_id)
        .offset(params.offset)
        .limit(params.limit)
    )
    results = result.scalars().all()
    
    response_items = [
        BusinessDataResponse(**(await result.to_dict()))
        for result in results
    ]
    
    return BusinessSearchResults.create(
        items=response_items,
        total=total,
        params=params
    )

@router.get("/stats", response_model=BusinessSearchStats)
async def get_search_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(
        select(func.count()).select_from(BusinessSearch).where(
            BusinessSearch.user_id == current_user.id
        )
    )
    total_searches = result.scalar_one()
    
    result = await db.execute(
        select(func.count()).select_from(BusinessSearch).where(
            BusinessSearch.user_id == current_user.id,
            BusinessSearch.status == SearchStatus.COMPLETED
        )
    )
    completed_searches = result.scalar_one()
    
    result = await db.execute(
        select(func.count()).select_from(BusinessSearch).where(
            BusinessSearch.user_id == current_user.id,
            BusinessSearch.status == SearchStatus.FAILED
        )
    )
    failed_searches = result.scalar_one()
    
    result = await db.execute(
        select(BusinessSearch.results_count).where(
            BusinessSearch.user_id == current_user.id,
            BusinessSearch.status == SearchStatus.COMPLETED
        )
    )
    results = result.scalars().all()
    average_results = sum(results) / completed_searches if completed_searches else 0
    
    result = await db.execute(
        select(
            BusinessSearch.business_type,
            func.count(BusinessSearch.id).label('count')
        )
        .where(BusinessSearch.user_id == current_user.id)
        .group_by(BusinessSearch.business_type)
        .order_by(func.count(BusinessSearch.id).desc())
        .limit(5)
    )
    most_searched_types = result.all()
    
    result = await db.execute(
        select(
            BusinessSearch.location,
            func.count(BusinessSearch.id).label('count')
        )
        .where(BusinessSearch.user_id == current_user.id)
        .group_by(BusinessSearch.location)
        .order_by(func.count(BusinessSearch.id).desc())
        .limit(5)
    )
    most_searched_locations = result.all()
    
    result = await db.execute(
        select(BusinessSearch)
        .where(BusinessSearch.user_id == current_user.id)
        .order_by(BusinessSearch.created_at.desc())
        .limit(1)
    )
    last_search = result.scalar_one_or_none()
    
    return BusinessSearchStats(
        total_searches=total_searches,
        completed_searches=completed_searches,
        failed_searches=failed_searches,
        average_results=average_results,
        most_searched_types=[{"type": t[0], "count": t[1]} for t in most_searched_types],
        most_searched_locations=[{"location": l[0], "count": l[1]} for l in most_searched_locations],
        last_search=last_search.created_at if last_search else None
    )

@router.get("/search/{search_id}/export/csv")
async def export_search_results_csv(
    search_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(
        select(BusinessSearch).where(
            BusinessSearch.id == search_id,
            BusinessSearch.user_id == current_user.id
        )
    )
    search = result.scalar_one_or_none()
    
    if not search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Search not found"
        )
    
    result = await db.execute(
        select(BusinessData).where(
            BusinessData.search_id == search_id
        )
    )
    results = result.scalars().all()
    
    csv_data = ExportService.to_csv(results)
    filename = ExportService.generate_filename(search.business_type, "csv")
    
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

@router.get("/details/{business_id}", response_model=BusinessDetailsResponse)
async def get_business_details(
    business_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(
        select(BusinessData).where(BusinessData.id == business_id)
    )
    business = result.scalar_one_or_none()
    
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found"
        )
    
    async with GooglePlacesService() as places_service:
        try:
            details = await places_service.get_place_details(business.place_id)
            if details and details.get("result"):
                place_data = places_service.process_place_data(
                    details["result"], 
                    fallback_id=business.place_id
                )
                
                for key, value in place_data.items():
                    if hasattr(business, key):
                        setattr(business, key, value)
                
                business.weekday_text = place_data.get("weekday_text", [])
                business.reviews = place_data.get("reviews", [])
                business.photos = place_data.get("photos", [])
                business.opening_hours = place_data.get("opening_hours", {})
                business.raw_data = place_data.get("raw_data", {})
                
                business.updated_at = datetime.utcnow()
                
                db.add(business)
                await db.commit()
        except Exception as e:
            logger.error(f"Error getting place details: {str(e)}")
            if business.weekday_text is None:
                business.weekday_text = []
            if business.reviews is None:
                business.reviews = []
    
    business_dict = await business.to_dict()
    business_dict.setdefault("weekday_text", [])
    business_dict.setdefault("reviews", [])
    business_dict.setdefault("formatted_phone_number", None)
    business_dict.setdefault("international_phone_number", None)
    
    return BusinessDetailsResponse(**business_dict)

@router.get("/search/{search_id}/export/xlsx")
async def export_search_results_xlsx(
    search_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(
        select(BusinessSearch).where(
            BusinessSearch.id == search_id,
            BusinessSearch.user_id == current_user.id
        )
    )
    search = result.scalar_one_or_none()
    
    if not search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Search not found"
        )
    
    result = await db.execute(
        select(BusinessData).where(
            BusinessData.search_id == search_id
        )
    )
    results = result.scalars().all()
    
    xlsx_data = ExportService.to_xlsx(results)
    filename = ExportService.generate_filename(search.business_type, "xlsx")
    
    return Response(
        content=xlsx_data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )