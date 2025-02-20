import asyncio
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from celery.result import AsyncResult

from app.core.database import get_db
from app.models.user import User
from app.models.whatsapp import WhatsAppAccount, WhatsAppAccountStatus
from app.worker.tasks import send_whatsapp_message, send_bulk_whatsapp_messages
from app.schemas.whatsapp import (
    WhatsAppAccountCreate,
    WhatsAppAccountUpdate,
    WhatsAppAccountResponse,
    WhatsAppMessageBulk,
    WhatsAppMessageResponse,
    WhatsAppSessionInit,
    WhatsAppSessionResponse,
    WhatsAppQRCodeResponse,
    WhatsAppMessageHistory
)
from app.core.redis import get_qr_code
from app.services.whatsapp import WhatsAppService
from app.api.v1.auth import get_current_user

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

@router.get("/accounts/{account_id}/qr", response_model=WhatsAppQRCodeResponse)
async def get_account_qr(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
):
    """Gets WhatsApp account QR code and status"""
    print(f"[DEBUG] QR code request for account {account_id}")
    
    async with db_session as db:
        whatsapp_service = WhatsAppService(db)
        account = await whatsapp_service.get_account(account_id)
        
        if not account:
            print(f"[DEBUG] Account {account_id} not found")
            raise HTTPException(status_code=404, detail="Account not found")
        
        if account.user_id != current_user.id:
            print(f"[DEBUG] Access denied to account {account_id}")
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Update account data to get current status
        await db.refresh(account)
        print(f"[DEBUG] Account {account_id} status: {account.status}")
        
        # If account is active, return status without QR code
        if account.status == WhatsAppAccountStatus.ACTIVE:
            print(f"[DEBUG] Account {account_id} is active, QR code not needed")
            return {
                "account_id": account_id,
                "qr_code": None,
                "status": account.status,
                "error": None,
                "metadata": account.account_metadata
            }
        
        # Get QR code from Redis
        qr_code = await get_qr_code(account_id)
        print(f"[DEBUG] QR code for {account_id}: {'Received' if qr_code else 'Missing'}")
        
        # Determine status and message based on current state
        status_message = None
        if account.status == WhatsAppAccountStatus.PENDING:
            if not qr_code:
                status_message = "Initializing WhatsApp..."
                print(f"[DEBUG] {account_id}: Waiting for QR code generation")
            else:
                status_message = "Waiting for QR code scan..."
                print(f"[DEBUG] {account_id}: QR code ready for scanning")
        elif account.status == WhatsAppAccountStatus.ERROR:
            status_message = "WhatsApp initialization error"
            print(f"[DEBUG] {account_id}: Initialization error")
        
        response = {
            "account_id": account_id,
            "qr_code": qr_code,
            "status": account.status,
            "error": status_message if account.status == WhatsAppAccountStatus.ERROR else None,
            "status_message": status_message,
            "metadata": account.account_metadata
        }
        
        print(f"[DEBUG] Sending response for {account_id}: status={account.status}, QR={'Present' if qr_code else 'Missing'}")
        return response

@router.get("/accounts/{account_id}/messages", response_model=List[WhatsAppMessageHistory])
async def get_message_history(
    account_id: str,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
):
    """Gets message history for the account"""
    async with db_session as db:
        whatsapp_service = WhatsAppService(db)
        account = await whatsapp_service.get_account(account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        if account.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        messages = await whatsapp_service.get_message_history(account_id, limit, offset)
        return messages


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Checks message sending task status
    """
    task_result = AsyncResult(task_id)
    
    response = {
        "task_id": task_id,
        "status": task_result.status,
        "done": task_result.ready()
    }
    
    # Add result if task is completed
    if task_result.ready():
        if task_result.successful():
            result = task_result.get()
            # Add message_id to response if present
            if isinstance(result, dict) and "message_id" in result:
                response["message_id"] = result["message_id"]
            response["result"] = result
        else:
            response["error"] = str(task_result.result)
            
    return response


@router.post("/accounts", response_model=WhatsAppAccountResponse)
async def create_account(
    account: WhatsAppAccountCreate,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
):
    """Creates new WhatsApp account"""
    async with db_session as db:
        # Check if account with this name already exists
        result = await db.execute(
            select(WhatsAppAccount).where(
                WhatsAppAccount.profile_name == account.profile_name
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Account with name {account.profile_name} already exists"
            )
        
        # Create new account
        db_account = WhatsAppAccount(
            **account.model_dump(),
            user_id=current_user.id
        )
        db.add(db_account)
        await db.commit()
        await db.refresh(db_account)
        
        return db_account


@router.get("/accounts", response_model=List[WhatsAppAccountResponse])
async def list_accounts(
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
):
    """Returns user's WhatsApp accounts list"""
    async with db_session as db:
        result = await db.execute(
            select(WhatsAppAccount)
            .where(WhatsAppAccount.user_id == current_user.id)
            .order_by(WhatsAppAccount.created_at.desc())
        )
        return result.scalars().all()


@router.get("/accounts/{account_id}", response_model=WhatsAppAccountResponse)
async def get_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
):
    """Returns WhatsApp account information"""
    async with db_session as db:
        result = await db.execute(
            select(WhatsAppAccount).where(
                WhatsAppAccount.id == account_id,
                WhatsAppAccount.user_id == current_user.id
            )
        )
        account = result.scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        return account


@router.patch("/accounts/{account_id}", response_model=WhatsAppAccountResponse)
async def update_account(
    account_id: str,
    account_update: WhatsAppAccountUpdate,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
):
    """Updates WhatsApp account information"""
    async with db_session as db:
        result = await db.execute(
            select(WhatsAppAccount).where(
                WhatsAppAccount.id == account_id,
                WhatsAppAccount.user_id == current_user.id
            )
        )
        account = result.scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        # Update fields
        for field, value in account_update.model_dump(exclude_unset=True).items():
            setattr(account, field, value)
        
        await db.commit()
        await db.refresh(account)
        return account


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
):
    """Completely deletes WhatsApp account and its profile"""
    async with db_session as db:
        whatsapp_service = WhatsAppService(db)
        account = await whatsapp_service.get_account(account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        if account.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        success = await whatsapp_service.delete_account(account)
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to delete account"
            )
        
        return {"success": True, "message": "Account successfully deleted"}


@router.post("/accounts/{account_id}/init", response_model=WhatsAppSessionResponse)
async def initialize_session(
    account_id: str,
    init_data: WhatsAppSessionInit,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
):
    """Initializes WhatsApp session"""
    async with db_session as db:
        whatsapp_service = WhatsAppService(db)
        account = await whatsapp_service.get_account(account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        if account.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        result = await whatsapp_service.initialize_session(
            account,
            wait_time=init_data.wait_time
        )
        return result


@router.post("/accounts/{account_id}/send")
async def send_messages(
    account_id: str,
    message_data: WhatsAppMessageBulk,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Sends messages via WhatsApp asynchronously using Celery
    Returns task ID for status tracking
    """
    async with db_session as db:
        whatsapp_service = WhatsAppService(db)
        account = await whatsapp_service.get_account(account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        if account.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not account.is_ready:
            raise HTTPException(
                status_code=400,
                detail="Account is not ready to send messages"
            )
        
        try:
            # Create message history records
            messages = []
            for recipient in message_data.recipients:
                message = await whatsapp_service.create_message_history(account, recipient)
                messages.append(message)

            # If single recipient, use send_whatsapp_message
            if len(message_data.recipients) == 1:
                task = send_whatsapp_message.delay(
                    account_id=account_id,
                    recipient_data=message_data.recipients[0].model_dump(),
                    message_id=str(messages[0].id),
                    wait_time=message_data.wait_time
                )
            # If multiple recipients, use send_bulk_whatsapp_messages
            else:
                task = send_bulk_whatsapp_messages.delay(
                    account_id=account_id,
                    recipients_data=[r.model_dump() for r in message_data.recipients],
                    message_ids=[str(m.id) for m in messages],
                    wait_time=message_data.wait_time
                )

            return {
                "task_id": task.id,
                "status": "accepted",
                "message": "Messages queued for sending",
                "recipients_count": len(message_data.recipients),
                "message_ids": [str(m.id) for m in messages]
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error queuing messages: {str(e)}"
            )