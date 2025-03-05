from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import logging
from typing import Optional

from app.core.database import get_db_session
from app.core.security import get_current_user
from app.models.user import User
from app.models.google_oauth import GoogleOAuth
from app.services.google_people import GooglePeopleService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/google", tags=["google"])

@router.get("/auth/url")
async def get_google_auth_url(
    current_user: User = Depends(get_current_user)
):
    """Generate a Google OAuth authorization URL"""
    # Use static method directly - no need to instantiate GooglePeopleService
    from app.core.config import settings
    
    # Log the OAuth configuration for debugging
    logger.info(f"Google OAuth Configuration - Client ID: '{settings.GOOGLE_OAUTH_CLIENT_ID="REMOVED"}'")
    logger.info(f"Google OAuth Configuration - Redirect URI: '{settings.GOOGLE_OAUTH_REDIRECT_URI}'")
    
    # Verify client_id is not empty
    if not settings.GOOGLE_OAUTH_CLIENT_ID="REMOVED":
        logger.error("GOOGLE_OAUTH_CLIENT_ID="REMOVED" is empty or not set")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth client ID not configured"
        )
    
    state = current_user.id  # Use user ID as state to verify callback
    auth_url = GooglePeopleService.generate_oauth_url(
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID="REMOVED",
        redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI,
        state=state
    )
    
    logger.info(f"Generated OAuth URL: {auth_url}")
    return {
        "auth_url": auth_url,
        "dev_mode_note": "Note: This app is in development mode. You may need to be added as a test user in Google Cloud Console to access it."
    }


@router.get("/auth/callback")
async def google_auth_callback(
    code: str = Query(...),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db_session)
):
    """Handle the Google OAuth callback"""
    if error:
        logger.error(f"OAuth error: {error}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Authentication error: {error}"
        )
    
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing state parameter"
        )
    
    try:
        # Find the user by ID (state contains user ID)
        result = await db.execute(select(User).where(User.id == state))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Exchange code for token using static method
        from app.core.config import settings
        
        # Log the OAuth configuration for callback
        logger.info(f"Google OAuth Callback - Client ID: '{settings.GOOGLE_OAUTH_CLIENT_ID="REMOVED"}'")
        logger.info(f"Google OAuth Callback - Redirect URI: '{settings.GOOGLE_OAUTH_REDIRECT_URI}'")
        
        # Verify client credentials are not empty
        if not settings.GOOGLE_OAUTH_CLIENT_ID="REMOVED":
            logger.error("GOOGLE_OAUTH_CLIENT_ID="REMOVED" is empty or not set during callback")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OAuth client ID not configured"
            )
            
        if not settings.GOOGLE_OAUTH_CLIENT_SECRET="REMOVED":
            logger.error("GOOGLE_OAUTH_CLIENT_SECRET="REMOVED" is empty or not set during callback")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OAuth client secret not configured"
            )
        
        logger.info(f"Exchanging code for tokens with code: {code[:5]}...")
        
        tokens = await GooglePeopleService.exchange_code_for_tokens(
            code=code,
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID="REMOVED",
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET="REMOVED",
            redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI
        )
        
        logger.info(f"Token exchange successful, received access token")
        
        # Check if user already has Google OAuth credentials
        result = await db.execute(
            select(GoogleOAuth).where(GoogleOAuth.user_id == user.id)
        )
        oauth = result.scalar_one_or_none()
        
        if oauth:
            # Update existing credentials
            oauth.access_token = tokens.get("access_token")
            oauth.refresh_token = tokens.get("refresh_token") or oauth.refresh_token  # Only update if provided
            oauth.token_type = tokens.get("token_type")
            oauth.expires_at = datetime.fromisoformat(tokens.get("expires_at")) if tokens.get("expires_at") else None
            oauth.is_active = True
        else:
            # Create new credentials with full contacts scope (including write permissions)
            oauth = GoogleOAuth(
                user_id=user.id,
                access_token=tokens.get("access_token"),
                refresh_token=tokens.get("refresh_token"),
                token_type=tokens.get("token_type"),
                expires_at=datetime.fromisoformat(tokens.get("expires_at")) if tokens.get("expires_at") else None,
                scopes=["https://www.googleapis.com/auth/contacts"],  # Full contacts scope with write permissions
                is_active=True
            )
            db.add(oauth)
        
        await db.commit()
        
        # Redirect to frontend with success message
        return {
            "status": "success",
            "message": "Successfully connected Google account",
            "user_id": user.id
        }
        
    except Exception as e:
        logger.error(f"Error in Google OAuth callback: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing OAuth callback"
        )


@router.get("/status", response_model=dict)
async def get_google_connection_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Check if the user has connected their Google account"""
    result = await db.execute(
        select(GoogleOAuth).where(
            GoogleOAuth.user_id == current_user.id,
            GoogleOAuth.is_active == True
        )
    )
    oauth = result.scalar_one_or_none()
    
    if not oauth:
        return {
            "connected": False,
            "message": "Google account not connected"
        }
    
    return {
        "connected": True,
        "email": oauth.account_email,
        "connected_at": oauth.created_at,
        "expires_at": oauth.expires_at,
        "is_token_valid": oauth.is_token_valid
    }


@router.delete("/disconnect")
async def disconnect_google_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Disconnect Google account"""
    result = await db.execute(
        select(GoogleOAuth).where(GoogleOAuth.user_id == current_user.id)
    )
    oauth = result.scalar_one_or_none()
    
    if not oauth:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Google account connected"
        )
    
    # Deactivate rather than delete to preserve refresh token if user reconnects
    oauth.is_active = False
    await db.commit()
    
    return {
        "status": "success",
        "message": "Successfully disconnected Google account"
    }