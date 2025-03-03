import asyncio
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from celery.result import AsyncResult
from datetime import datetime

from app.core.database import get_db
from app.models.user import User
from app.models.whatsapp import WhatsAppAccount, WhatsAppAccountStatus
from app.worker.tasks.whatsapp import (
    send_whatsapp_message, 
    send_bulk_whatsapp_messages,
    check_whatsapp_account_status,
    logout_whatsapp_account
)
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
from app.core.redis import get_qr_code, check_auth_status, delete_qr_code, reset_auth_status
from app.services.whatsapp import WhatsAppService
from app.api.v1.auth import get_current_user
# Настраиваем логгер
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

@router.get("/accounts/{account_id}/qr", response_model=WhatsAppQRCodeResponse)
async def get_account_qr(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
):
    """
    Получает QR-код и статус аккаунта WhatsApp
    
    Args:
        account_id: ID аккаунта
        current_user: Текущий пользователь
        db_session: Сессия базы данных
        
    Returns:
        Информация о QR-коде и статусе аккаунта
    """
    async with db_session as db:
        whatsapp_service = WhatsAppService(db)
        account = await whatsapp_service.get_account(account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        if account.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Важно! Обновляем данные аккаунта из базы для получения актуального статуса
        await db.refresh(account)
        
        # Важно! Проверяем текущее состояние аккаунта в базе данных
        stmt = select(WhatsAppAccount).where(WhatsAppAccount.id == account_id).with_for_update()
        result = await db.execute(stmt)
        updated_account = result.scalar_one_or_none()
        
        # Если аккаунт не найден или был удален
        if not updated_account:
            return {
                "account_id": account_id,
                "qr_code": None,
                "status": "error",
                "error": "Account not found or deleted",
                "status_message": "Account not found",
                "metadata": {},
                "authenticated": False,
                "close_modal": True  # Закрываем модальное окно в случае ошибки
            }
        
        # Используем обновленный объект аккаунта
        account = updated_account
        
        # Проверка статуса авторизации в Redis
        auth_status = await check_auth_status(account_id)
        
        # Получаем QR-код из Redis
        qr_code = await get_qr_code(account_id)
        
        # Если аккаунт активен, автентификация в Redis или QR-код исчез - считаем что авторизованы
        if (account.status == WhatsAppAccountStatus.ACTIVE or 
            auth_status or 
            (account.status == WhatsAppAccountStatus.PENDING and 
             not qr_code and 
             account.account_metadata and 
             account.account_metadata.get("qr_shown", False))):
            
            # Если аккаунт все еще в статусе PENDING, но по другим признакам авторизован,
            # обновляем его статус на ACTIVE
            if account.status != WhatsAppAccountStatus.ACTIVE:
                account.status = WhatsAppAccountStatus.ACTIVE
                if not account.account_metadata:
                    account.account_metadata = {}
                account.account_metadata["last_active"] = datetime.now().isoformat()
                await db.commit()
            # Удаляем QR-код из Redis если есть
            await delete_qr_code(account_id)
            
            return {
                "account_id": account_id,
                "qr_code": None,
                "status": WhatsAppAccountStatus.ACTIVE,
                "error": None,
                "status_message": "WhatsApp is connected",
                "metadata": account.account_metadata,
                "authenticated": True,     # Установка флага аутентификации
                "close_modal": True        # Сигнал для закрытия модального окна
            }
            
        # Проверяем по логам: Если был QR-код, но сейчас его нет, значит он был отсканирован
        # В логах мы видим "QR code disappeared" перед успешной аутентификацией
        if not qr_code and account.status == WhatsAppAccountStatus.PENDING:
            # Проверка, был ли QR-код ранее и сейчас исчез
            # Если у аккаунта есть метаданные и в них указано, что QR был показан
            was_qr_shown = False
            if account.account_metadata and isinstance(account.account_metadata, dict):
                was_qr_shown = account.account_metadata.get("qr_shown", False)
                
            # Если QR-код не получен, но ранее был показан - считаем что произошла аутентификация
            if was_qr_shown:
                # Обновляем статус аккаунта на ACTIVE
                account.status = WhatsAppAccountStatus.ACTIVE
                if not account.account_metadata:
                    account.account_metadata = {}
                account.account_metadata["last_active"] = datetime.now().isoformat()
                await db.commit()
                
                # Удаляем QR-код из Redis
                await delete_qr_code(account_id)
                
                return {
                    "account_id": account_id,
                    "qr_code": None,
                    "status": WhatsAppAccountStatus.ACTIVE,
                    "error": None,
                    "status_message": "WhatsApp connected successfully",
                    "metadata": account.account_metadata,
                    "authenticated": True,
                    "close_modal": True
                }
        
        # Если QR-код найден, отмечаем в метаданных аккаунта, что QR был показан
        if qr_code:
            if not account.account_metadata:
                account.account_metadata = {}
            account.account_metadata["qr_shown"] = True
            await db.commit()
        
        # Определяем статус и сообщение на основе текущего состояния
        status_message = None
        if account.status == WhatsAppAccountStatus.PENDING:
            if not qr_code:
                status_message = "Initializing WhatsApp..."
            else:
                status_message = "Waiting for QR code scan..."
        elif account.status == WhatsAppAccountStatus.ERROR:
            error_message = "WhatsApp initialization error"
            if account.account_metadata and isinstance(account.account_metadata, dict):
                error_message = account.account_metadata.get("last_error", error_message)
            status_message = error_message
        
        response = {
            "account_id": account_id,
            "qr_code": qr_code,
            "status": account.status,
            "error": status_message if account.status == WhatsAppAccountStatus.ERROR else None,
            "status_message": status_message,
            "metadata": account.account_metadata,
            "authenticated": False,      # По умолчанию не аутентифицирован
            "close_modal": False         # По умолчанию не закрываем окно
        }
        
        return response

@router.get("/accounts/{account_id}/messages", response_model=List[WhatsAppMessageHistory])
async def get_message_history(
    account_id: str,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
):
    """
    Получает историю сообщений для аккаунта
    
    Args:
        account_id: ID аккаунта
        limit: Максимальное количество сообщений
        offset: Смещение для пагинации
        current_user: Текущий пользователь
        db_session: Сессия базы данных
        
    Returns:
        Список сообщений
    """
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
    Проверяет статус задачи отправки сообщения
    
    Args:
        task_id: ID задачи Celery
        
    Returns:
        Информация о статусе задачи
    """
    task_result = AsyncResult(task_id)
    
    response = {
        "task_id": task_id,
        "status": task_result.status,
        "done": task_result.ready()
    }
    
    # Добавляем результат, если задача завершена
    if task_result.ready():
        if task_result.successful():
            result = task_result.get()
            # Добавляем ID сообщения в ответ, если он есть
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
    """
    Создает новый аккаунт WhatsApp
    
    Args:
        account: Данные аккаунта
        current_user: Текущий пользователь
        db_session: Сессия базы данных
        
    Returns:
        Созданный аккаунт
    """
    async with db_session as db:
        # Проверяем, существует ли аккаунт с таким именем
        result = await db.execute(
            select(WhatsAppAccount).where(
                WhatsAppAccount.profile_name == account.profile_name,
                WhatsAppAccount.user_id == current_user.id
            )
        )
        
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Account with name {account.profile_name} already exists"
            )
        
        # Создаем новый аккаунт
        try:
            db_account = WhatsAppAccount(
                **account.model_dump(),
                user_id=current_user.id,
                status=WhatsAppAccountStatus.PENDING,
                account_metadata={"created_at": datetime.now().isoformat()}
            )
            
            db.add(db_account)
            await db.commit()
            await db.refresh(db_account)
            
            return db_account
        except Exception as e:
            await db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create account: {str(e)}"
            )


@router.get("/accounts", response_model=List[WhatsAppAccountResponse])
async def list_accounts(
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
):
    """
    Возвращает список аккаунтов WhatsApp пользователя
    
    Args:
        current_user: Текущий пользователь
        db_session: Сессия базы данных
        
    Returns:
        Список аккаунтов
    """
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
    """
    Возвращает информацию об аккаунте WhatsApp
    
    Args:
        account_id: ID аккаунта
        current_user: Текущий пользователь
        db_session: Сессия базы данных
        
    Returns:
        Информация об аккаунте
    """
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
    """
    Обновляет информацию об аккаунте WhatsApp
    
    Args:
        account_id: ID аккаунта
        account_update: Данные для обновления
        current_user: Текущий пользователь
        db_session: Сессия базы данных
        
    Returns:
        Обновленная информация об аккаунте
    """
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
        
        # Обновляем поля
        update_data = account_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(account, field, value)
        
        try:
            await db.commit()
            await db.refresh(account)
            return account
        except Exception as e:
            await db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update account: {str(e)}"
            )


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
):
    """
    Полностью удаляет аккаунт WhatsApp и его профиль
    
    Args:
        account_id: ID аккаунта
        current_user: Текущий пользователь
        db_session: Сессия базы данных
        
    Returns:
        Результат операции
    """
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
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
):
    """
    Инициализирует сессию WhatsApp
    
    Args:
        account_id: ID аккаунта
        init_data: Данные для инициализации
        background_tasks: Фоновые задачи FastAPI
        current_user: Текущий пользователь
        db_session: Сессия базы данных
        
    Returns:
        Результат инициализации
    """
    async with db_session as db:
        whatsapp_service = WhatsAppService(db)
        account = await whatsapp_service.get_account(account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        if account.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # При инициализации всегда сбрасываем статус на PENDING
        # и очищаем статус аутентификации в Redis
        account.status = WhatsAppAccountStatus.PENDING
        await db.commit()
        
        # Полностью сбрасываем статус аутентификации в Redis без установки новой метки
        await reset_auth_status(account_id)
        
        async def initialize_in_background():
            try:
                await whatsapp_service.initialize_session(
                    account,
                    wait_time=init_data.wait_time
                )
            except Exception as e:
                logger.error(f"Background initialization error: {str(e)}")
        
        # Запускаем инициализацию в фоновом режиме
        background_tasks.add_task(initialize_in_background)
        
        # Возвращаем начальный ответ
        return {
            "success": True,
            "account_id": account_id,
            "status": account.status,
            "qr_code": await get_qr_code(account_id),
            "message": "Initialization started"
        }


@router.post("/accounts/{account_id}/check")
async def check_account_status(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
):
    """
    Проверяет статус аккаунта WhatsApp
    
    Args:
        account_id: ID аккаунта
        current_user: Текущий пользователь
        db_session: Сессия базы данных
        
    Returns:
        Задача для проверки статуса
    """
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
        
        task = check_whatsapp_account_status.delay(account_id)
        
        return {
            "task_id": task.id,
            "message": "Status check scheduled"
        }


@router.post("/accounts/{account_id}/logout")
async def logout_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
):
    """
    Выполняет выход из аккаунта WhatsApp
    
    Args:
        account_id: ID аккаунта
        current_user: Текущий пользователь
        db_session: Сессия базы данных
        
    Returns:
        Задача для выполнения выхода
    """
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
        
        task = logout_whatsapp_account.delay(account_id)
        
        return {
            "task_id": task.id,
            "message": "Logout scheduled"
        }


@router.post("/accounts/{account_id}/send")
async def send_messages(
    account_id: str,
    message_data: WhatsAppMessageBulk,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Отправляет сообщения через WhatsApp асинхронно с использованием Celery
    Возвращает идентификатор задачи для отслеживания статуса
    
    Args:
        account_id: ID аккаунта
        message_data: Данные сообщения
        current_user: Текущий пользователь
        db_session: Сессия базы данных
        
    Returns:
        Информация о задаче
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
            # Создаем записи истории сообщений
            messages = []
            for recipient in message_data.recipients:
                message = await whatsapp_service.create_message_history(account, recipient)
                messages.append(message)

            # Если один получатель, используем send_whatsapp_message
            if len(message_data.recipients) == 1:
                task = send_whatsapp_message.delay(
                    account_id=account_id,
                    recipient_data=message_data.recipients[0].model_dump(),
                    message_id=str(messages[0].id),
                    wait_time=message_data.wait_time
                )
            # Если несколько получателей, используем send_bulk_whatsapp_messages
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
            # В случае ошибки, возвращаем информативное сообщение
            logger.error(f"Error sending messages: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error sending messages: {str(e)}"
            )