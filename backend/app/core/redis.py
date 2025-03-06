from redis import asyncio as aioredis
from redis.exceptions import RedisError
from app.core.config import settings
import json
from typing import Optional, Dict, List, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

try:
    redis = aioredis.from_url(
        f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
        password=settings.REDIS_PASSWORD="REMOVED",
        encoding="utf-8",
        decode_responses=True,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT
    )
except Exception as e:
    raise

async def get_qr_code(account_id: str) -> str:
    """
    Получает QR-код из Redis для аккаунта.
    
    Args:
        account_id: ID аккаунта WhatsApp
        
    Returns:
        Строка с QR-кодом в формате base64 или None
    """
    key = f"whatsapp:qr:{account_id}"
    try:
        await redis.ping()
        
        # Проверяем статус аккаунта в Redis (метки для авторизации)
        auth_key = f"whatsapp:auth:{account_id}"
        account_authorized = await redis.get(auth_key)
        
        # Если аккаунт авторизован, возвращаем None вместо QR-кода
        if account_authorized:
            # Удаляем QR-код если он существует
            await redis.delete(key)
            return None
        
        # Иначе возвращаем QR-код если он существует
        qr_code = await redis.get(key)
        return qr_code
    except RedisError as e:
        logger.error(f"Redis error in get_qr_code: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_qr_code: {str(e)}")
        return None

async def set_qr_code(account_id: str, qr_code: str, expire: int = 120) -> None:
    """
    Сохраняет QR-код в Redis.
    
    Args:
        account_id: ID аккаунта WhatsApp
        qr_code: QR-код в формате base64
        expire: Время жизни QR-кода в секундах
    """
    key = f"whatsapp:qr:{account_id}"
    try:
        await redis.ping()
        
        # Удаляем метку авторизации если она есть
        auth_key = f"whatsapp:auth:{account_id}"
        await redis.delete(auth_key)
        
        # Сохраняем QR-код
        await redis.set(key, qr_code, ex=expire)
        
        # Проверяем, что QR-код действительно сохранился
        saved_qr = await redis.get(key)
        if not saved_qr:
            logger.warning(f"QR code for account {account_id} was not saved in Redis")
    except RedisError as e:
        logger.error(f"Redis error in set_qr_code: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in set_qr_code: {str(e)}")
        raise

async def delete_qr_code(account_id: str) -> None:
    """
    Удаляет QR-код из Redis и устанавливает метку авторизации.
    
    Args:
        account_id: ID аккаунта WhatsApp
    """
    key = f"whatsapp:qr:{account_id}"
    auth_key = f"whatsapp:auth:{account_id}"
    try:
        await redis.ping()
        
        # Удаляем QR-код
        await redis.delete(key)
        
        # Устанавливаем метку авторизации (на 24 часа)
        await redis.set(auth_key, "1", ex=86400)
    except RedisError as e:
        logger.error(f"Redis error in delete_qr_code: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in delete_qr_code: {str(e)}")
        raise

async def reset_auth_status(account_id: str) -> None:
    """
    Полностью сбрасывает статус аутентификации и QR-код без установки новой метки.
    Используется при инициализации новой сессии.
    
    Args:
        account_id: ID аккаунта WhatsApp
    """
    qr_key = f"whatsapp:qr:{account_id}"
    auth_key = f"whatsapp:auth:{account_id}"
    try:
        await redis.ping()
        
        # Удаляем и QR-код, и метку авторизации
        await redis.delete(qr_key)
        await redis.delete(auth_key)
    except RedisError as e:
        logger.error(f"Redis error in reset_auth_status: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in reset_auth_status: {str(e)}")
        raise

async def check_auth_status(account_id: str) -> bool:
    """
    Проверяет статус авторизации аккаунта в Redis.
    
    Args:
        account_id: ID аккаунта WhatsApp
        
    Returns:
        True если аккаунт авторизован, иначе False
    """
    auth_key = f"whatsapp:auth:{account_id}"
    try:
        await redis.ping()
        
        # Проверяем наличие метки авторизации
        account_authorized = await redis.get(auth_key)
        return bool(account_authorized)
    except Exception as e:
        logger.error(f"Error checking auth status: {str(e)}")
        return False

async def cache_business_search(
    search_query: str,
    location: str,
    radius: int,
    results: List[Dict],
    expire: int = 3600
) -> None:
    key = f"business:search:{search_query}:{location}:{radius}"

    await redis.set(
        key,
        json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            "results": results
        }),
        ex=expire
    )


async def get_cached_business_search(
    search_query: str,
    location: str,
    radius: int
) -> Optional[List[Dict]]:
    key = f"business:search:{search_query}:{location}:{radius}"
    try:
        data = await redis.get(key)
        if data:
            cached = json.loads(data)
            cache_time = datetime.fromisoformat(cached["timestamp"])
            if (datetime.utcnow() - cache_time).total_seconds() < 3600:
                return cached["results"]
        return None
    except Exception as e:
        return None

async def cache_place_details(
    place_id: str,
    details: Dict,
    expire: int = 86400
) -> None:
    key = f"business:place:{place_id}"
    try:
        await redis.set(
            key,
            json.dumps({
                "timestamp": datetime.utcnow().isoformat(),
                "details": details
            }),
            ex=expire
        )
    except Exception as e:
        print(f"Error: {str(e)}")

async def get_cached_place_details(place_id: str) -> Optional[Dict]:
    key = f"business:place:{place_id}"
    try:
        data = await redis.get(key)
        if data:
            cached = json.loads(data)
            cache_time = datetime.fromisoformat(cached["timestamp"])
            if (datetime.utcnow() - cache_time).total_seconds() < 86400:
                return cached["details"]
        return None
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return None

async def cache_location_coordinates(
    location: str,
    coordinates: Dict[str, float],
    expire: int = 604800
) -> None:
    key = f"business:location:{location}"
    try:
        await redis.set(
            key,
            json.dumps({
                "timestamp": datetime.utcnow().isoformat(),
                "coordinates": coordinates
            }),
            ex=expire
        )
    except Exception as e:
        print(f"ERROR: {str(e)}")

async def get_cached_location_coordinates(location: str) -> Optional[Dict[str, float]]:
    key = f"business:location:{location}"
    try:
        data = await redis.get(key)
        if data:
            cached = json.loads(data)
            cache_time = datetime.fromisoformat(cached["timestamp"])
            if (datetime.utcnow() - cache_time).total_seconds() < 604800:
                return cached["coordinates"]
        return None
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return None
    key = f"whatsapp:qr:{account_id}"
    try:
        # Проверяем подключение
        await redis.ping()
        await redis.delete(key)
    except RedisError as e:
        raise
    except Exception as e:
        raise