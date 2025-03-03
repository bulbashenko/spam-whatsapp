from typing import Dict, Any, List, Optional
import logging
from sqlalchemy import select

from app.worker.celery_app import celery_app
from app.worker.base import DatabaseTask
from app.services.whatsapp import WhatsAppService
from app.schemas.whatsapp import WhatsAppMessageRecipient
from app.models.whatsapp import WhatsAppMessage, WhatsAppMessageStatus

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, base=DatabaseTask, max_retries=3, retry_backoff=True)
def send_whatsapp_message(
    self,
    account_id: str,
    recipient_data: Dict[str, Any],
    message_id: Optional[str] = None,
    wait_time: int = 60
) -> Dict[str, Any]:
    """
    Celery задача для отправки сообщения WhatsApp
    
    Args:
        self: Экземпляр задачи
        account_id: ID аккаунта WhatsApp
        recipient_data: Данные получателя (словарь с phone и message)
        message_id: ID сообщения (опционально)
        wait_time: Максимальное время ожидания (в секундах)
        
    Returns:
        Словарь с результатами отправки
    """
    async def _send():
        async with self.db_session() as db:
            try:
                service = WhatsAppService(db)
                
                # Получаем аккаунт
                account = await service.get_account(account_id)
                if not account:
                    logger.error(f"WhatsApp account {account_id} not found")
                    raise ValueError(f"WhatsApp account {account_id} not found")
                
                # Проверяем формат данных сообщения
                if isinstance(recipient_data.get('message'), (list, tuple)):
                    recipient_data['message'] = ' '.join(map(str, recipient_data['message']))
                elif recipient_data.get('message') is not None:
                    recipient_data['message'] = str(recipient_data['message'])
                else:
                    recipient_data['message'] = ""
                
                # Создаем объект получателя
                recipient = WhatsAppMessageRecipient(**recipient_data)
                
                # Отправляем сообщение
                result = await service.send_message(
                    account=account,
                    recipient=recipient,
                    message_id=message_id,
                    wait_time=wait_time
                )
                
                return result
            except Exception as e:
                logger.error(f"Error in send_whatsapp_message task: {str(e)}")
                
                # В случае ошибки, обновляем статус сообщения на ERROR
                if message_id:
                    try:
                        result = await db.execute(
                            select(WhatsAppMessage).where(WhatsAppMessage.id == message_id)
                        )
                        message = result.scalar_one_or_none()
                        if message:
                            message.status = WhatsAppMessageStatus.ERROR
                            message.error_message = str(e)
                            await db.commit()
                    except Exception as db_err:
                        logger.error(f"Error updating message status: {str(db_err)}")
                
                raise

    try:
        return self.run_async(_send())
    except Exception as e:
        logger.error(f"Error sending WhatsApp message: {str(e)}")
        self.retry(exc=e, countdown=30)

@celery_app.task(bind=True, base=DatabaseTask, max_retries=3, retry_backoff=True)
def send_bulk_whatsapp_messages(
    self,
    account_id: str,
    recipients_data: List[Dict[str, Any]],
    message_ids: Optional[List[str]] = None,
    wait_time: int = 60
) -> List[Dict[str, Any]]:
    """
    Celery задача для массовой отправки сообщений WhatsApp
    
    Args:
        self: Экземпляр задачи
        account_id: ID аккаунта WhatsApp
        recipients_data: Список словарей с данными получателей
        message_ids: Список ID сообщений (опционально)
        wait_time: Максимальное время ожидания (в секундах)
        
    Returns:
        Список словарей с результатами отправки
    """
    async def _send_bulk():
        async with self.db_session() as db:
            try:
                service = WhatsAppService(db)
                
                # Получаем аккаунт
                account = await service.get_account(account_id)
                if not account:
                    logger.error(f"WhatsApp account {account_id} not found")
                    raise ValueError(f"WhatsApp account {account_id} not found")
                
                # Обрабатываем данные получателей
                processed_recipients = []
                for data in recipients_data:
                    # Нормализуем сообщение
                    if isinstance(data.get('message'), (list, tuple)):
                        data['message'] = ' '.join(map(str, data['message']))
                    elif data.get('message') is not None:
                        data['message'] = str(data['message'])
                    else:
                        data['message'] = ""
                    
                    processed_recipients.append(WhatsAppMessageRecipient(**data))
                
                # Отправляем сообщения
                return await service.send_bulk_messages(
                    account=account,
                    recipients=processed_recipients,
                    message_ids=message_ids,
                    wait_time=wait_time
                )
            except Exception as e:
                logger.error(f"Error in send_bulk_whatsapp_messages task: {str(e)}")
                
                # В случае ошибки, обновляем статусы сообщений
                if message_ids:
                    try:
                        for message_id in message_ids:
                            result = await db.execute(
                                select(WhatsAppMessage).where(WhatsAppMessage.id == message_id)
                            )
                            message = result.scalar_one_or_none()
                            if message:
                                message.status = WhatsAppMessageStatus.ERROR
                                message.error_message = str(e)
                        await db.commit()
                    except Exception as db_err:
                        logger.error(f"Error updating message statuses: {str(db_err)}")
                
                raise

    try:
        return self.run_async(_send_bulk())
    except Exception as e:
        logger.error(f"Error sending bulk WhatsApp messages: {str(e)}")
        self.retry(exc=e, countdown=60)

@celery_app.task(bind=True, base=DatabaseTask, max_retries=3, retry_backoff=True)
def check_whatsapp_account_status(self, account_id: str) -> Dict[str, Any]:
    """
    Celery задача для проверки статуса аккаунта WhatsApp
    
    Args:
        self: Экземпляр задачи
        account_id: ID аккаунта WhatsApp
        
    Returns:
        Словарь с информацией о статусе аккаунта
    """
    async def _check_status():
        async with self.db_session() as db:
            try:
                service = WhatsAppService(db)
                
                # Получаем аккаунт
                account = await service.get_account(account_id)
                if not account:
                    logger.error(f"WhatsApp account {account_id} not found")
                    raise ValueError(f"WhatsApp account {account_id} not found")
                
                # Проверяем статус
                return await service.check_account_status(account)
            except Exception as e:
                logger.error(f"Error checking WhatsApp account status: {str(e)}")
                raise

    try:
        return self.run_async(_check_status())
    except Exception as e:
        logger.error(f"Error checking WhatsApp account status: {str(e)}")
        self.retry(exc=e, countdown=30)

@celery_app.task(bind=True, base=DatabaseTask, max_retries=3, retry_backoff=True)
def logout_whatsapp_account(self, account_id: str) -> Dict[str, Any]:
    """
    Celery задача для выхода из аккаунта WhatsApp
    
    Args:
        self: Экземпляр задачи
        account_id: ID аккаунта WhatsApp
        
    Returns:
        Словарь с результатами операции
    """
    async def _logout():
        async with self.db_session() as db:
            try:
                service = WhatsAppService(db)
                
                # Получаем аккаунт
                account = await service.get_account(account_id)
                if not account:
                    logger.error(f"WhatsApp account {account_id} not found")
                    raise ValueError(f"WhatsApp account {account_id} not found")
                
                # Выполняем выход
                success = await service.logout(account)
                
                return {
                    "success": success,
                    "account_id": account_id,
                    "message": "Successfully logged out" if success else "Failed to log out"
                }
            except Exception as e:
                logger.error(f"Error logging out WhatsApp account: {str(e)}")
                raise

    try:
        return self.run_async(_logout())
    except Exception as e:
        logger.error(f"Error logging out WhatsApp account: {str(e)}")
        self.retry(exc=e, countdown=30)