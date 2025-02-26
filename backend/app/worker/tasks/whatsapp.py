from typing import Dict, Any, List
import logging
from sqlalchemy import select

from app.worker.celery_app import celery_app
from app.worker.base import DatabaseTask
from app.services.whatsapp import WhatsAppService
from app.schemas.whatsapp import WhatsAppMessageRecipient
from app.models.whatsapp import WhatsAppMessage, WhatsAppMessageStatus

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, base=DatabaseTask, max_retries=3)
def send_whatsapp_message(
    self,
    account_id: str,
    recipient_data: Dict[str, Any],
    message_id: str,
    wait_time: int = 60
) -> Dict[str, Any]:
    """
    Celery task to send a single WhatsApp message
    """
    async def _send():
        async with self.db_session() as db:
            service = WhatsAppService(db)
            
            # Get account and message
            account = await service.get_account(account_id)
            if not account:
                logger.error(f"WhatsApp account {account_id} not found")
                raise ValueError(f"WhatsApp account {account_id} not found")
            
            # Ensure message is a string in recipient data
            if isinstance(recipient_data.get('message'), (list, tuple)):
                recipient_data['message'] = ' '.join(map(str, recipient_data['message']))
            elif recipient_data.get('message') is not None:
                recipient_data['message'] = str(recipient_data['message'])
            
            # Create recipient object
            recipient = WhatsAppMessageRecipient(**recipient_data)
            
            # Send message using existing message record
            return await service.send_message(
                account=account,
                recipient=recipient,
                message_id=message_id,
                wait_time=wait_time
            )

    try:
        return self.run_async(_send())
    except Exception as e:
        logger.error(f"Error sending WhatsApp message: {str(e)}")
        async def update_status():
            async with self.db_session() as db:
                result = await db.execute(
                    select(WhatsAppMessage).where(WhatsAppMessage.id == message_id)
                )
                message = result.scalar_one_or_none()
                if message:
                    message.status = WhatsAppMessageStatus.ERROR
                    message.error_message = str(e)
                    await db.commit()

        try:
            self.run_async(update_status())
        except Exception as inner_e:
            logger.error(f"Failed to update message status: {str(inner_e)}")
        
        self.retry(exc=e, countdown=30)

@celery_app.task(bind=True, base=DatabaseTask, max_retries=3)
def send_bulk_whatsapp_messages(
    self,
    account_id: str,
    recipients_data: List[Dict[str, Any]],
    message_ids: List[str],
    wait_time: int = 60
) -> List[Dict[str, Any]]:
    """
    Celery task to send multiple WhatsApp messages
    """
    async def _send_bulk():
        async with self.db_session() as db:
            service = WhatsAppService(db)
            
            # Get account
            account = await service.get_account(account_id)
            if not account:
                logger.error(f"WhatsApp account {account_id} not found")
                raise ValueError(f"WhatsApp account {account_id} not found")
            
            # Process recipient data and create recipient objects
            processed_recipients = []
            for data in recipients_data:
                # Ensure message is a string
                if isinstance(data.get('message'), (list, tuple)):
                    data['message'] = ' '.join(map(str, data['message']))
                elif data.get('message') is not None:
                    data['message'] = str(data['message'])
                processed_recipients.append(WhatsAppMessageRecipient(**data))
            
            # Send messages with existing message IDs
            return await service.send_bulk_messages(
                account=account,
                recipients=processed_recipients,
                message_ids=message_ids,
                wait_time=wait_time
            )

    try:
        return self.run_async(_send_bulk())
    except Exception as e:
        logger.error(f"Error sending bulk WhatsApp messages: {str(e)}")
        async def update_statuses():
            async with self.db_session() as db:
                for message_id in message_ids:
                    result = await db.execute(
                        select(WhatsAppMessage).where(WhatsAppMessage.id == message_id)
                    )
                    message = result.scalar_one_or_none()
                    if message:
                        message.status = WhatsAppMessageStatus.ERROR
                        message.error_message = str(e)
                await db.commit()

        try:
            self.run_async(update_statuses())
        except Exception as inner_e:
            logger.error(f"Failed to update message statuses: {str(inner_e)}")
        
        self.retry(exc=e, countdown=30)