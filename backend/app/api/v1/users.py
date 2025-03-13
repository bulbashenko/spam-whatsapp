from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func


from app.core.database import get_db_session
from app.core.security import (
    get_current_user,
    get_password_hash,
    verify_password,
    check_user_role
)
from app.models.user import User, UserRole
from app.models.business_search import BusinessSearch, SearchStatus
from app.schemas.user import UserUpdate, UserResponse
from app.schemas.business import BusinessSearchResponse
from app.schemas.base import PaginationParams, PaginatedResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """Get current user's profile."""
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_user_profile(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    if user_data.email and user_data.email != current_user.email:
        if db.query(User).filter(User.email == user_data.email).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        current_user.email = user_data.email
    
    if user_data.password:
        current_user.hashed_password = get_password_hash(user_data.password)
    
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    current_password: str,
    new_password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    if not verify_password(current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password"
        )
    
    current_user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    return {"message": "Password updated successfully"}


@router.get("/search-history", response_model=PaginatedResponse)
async def get_search_history(
    params: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)  # Ensure AsyncSession is used
):
    total_stmt = select(func.count()).select_from(BusinessSearch).where(
        BusinessSearch.user_id == current_user.id
    )
    total_result = await db.execute(total_stmt)
    total = total_result.scalar()  # Get the count result

    search_stmt = (
        select(BusinessSearch)
        .where(BusinessSearch.user_id == current_user.id)
        .order_by(BusinessSearch.created_at.desc())
        .offset(params.offset)
        .limit(params.limit)
    )
    search_result = await db.execute(search_stmt)
    searches = search_result.scalars().all()  # Extract list of results

    return PaginatedResponse.create(
        items=[BusinessSearchResponse.from_orm(s) for s in searches],
        total=total,
        params=params
    )



@router.delete("/search-history/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_search(
    search_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    stmt = select(BusinessSearch).where(
        BusinessSearch.id == search_id,
        BusinessSearch.user_id == current_user.id
    )
    result = await db.execute(stmt)
    search = result.scalar_one_or_none()

    if not search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Search not found"
        )
    
    await db.delete(search)
    await db.commit()


@router.get("/recent-activity", response_model=List[BusinessSearchResponse])
async def get_recent_activity(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    recent_searches = db.query(BusinessSearch).filter(
        BusinessSearch.user_id == current_user.id,
        BusinessSearch.created_at >= datetime.utcnow() - timedelta(days=7)
    ).order_by(
        BusinessSearch.created_at.desc()
    ).limit(5).all()
    
    return recent_searches


@router.get(
    "/all",
    response_model=List[UserResponse],
    dependencies=[Depends(check_user_role(UserRole.ADMIN))]
)
async def get_all_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db_session)
):
    users = db.query(User).offset(skip).limit(limit).all()
    return users


@router.put(
    "/{user_id}/status",
    response_model=UserResponse,
    dependencies=[Depends(check_user_role(UserRole.ADMIN))]
)
async def update_user_status(
    user_id: int,
    is_active: bool,
    db: Session = Depends(get_db_session)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user