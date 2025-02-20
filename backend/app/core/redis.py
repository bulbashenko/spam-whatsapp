from redis import asyncio as aioredis
from redis.exceptions import RedisError
from app.core.config import settings

print(f"[DEBUG] Подключение к Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}")

try:
    redis = aioredis.from_url(
        f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
        password=settings.REDIS_PASSWORD="REMOVED",
        encoding="utf-8",
        decode_responses=True,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT
    )
    print("[DEBUG] Redis клиент создан успешно")
except Exception as e:
    print(f"[ERROR] Ошибка создания Redis клиента: {str(e)}")
    raise

async def get_qr_code(account_id: str) -> str:
    """Получает QR-код из Redis"""
    key = f"whatsapp:qr:{account_id}"
    try:
        # Проверяем подключение
        await redis.ping()
        print("[DEBUG] Redis подключение активно")
        
        qr_code = await redis.get(key)
        print(f"[DEBUG] Redis GET {key}: {'Found' if qr_code else 'Not found'}")
        if qr_code:
            print(f"[DEBUG] Размер QR кода: {len(qr_code)} bytes")
        return qr_code
    except RedisError as e:
        print(f"[ERROR] Ошибка получения QR кода из Redis: {str(e)}")
        return None
    except Exception as e:
        print(f"[ERROR] Неожиданная ошибка при работе с Redis: {str(e)}")
        return None

async def set_qr_code(account_id: str, qr_code: str, expire: int = 300) -> None:
    """Сохраняет QR-код в Redis с временем жизни"""
    key = f"whatsapp:qr:{account_id}"
    try:
        # Проверяем подключение
        await redis.ping()
        print("[DEBUG] Redis подключение активно")
        
        print(f"[DEBUG] Redis SET {key}: {len(qr_code) if qr_code else 0} bytes")
        await redis.set(key, qr_code, ex=expire)  # Expire через 5 минут
        
        # Проверяем, что QR код действительно сохранился
        saved_qr = await redis.get(key)
        print(f"[DEBUG] Redis Verification {key}: {'Saved' if saved_qr else 'Failed'}")
        if saved_qr:
            print(f"[DEBUG] Сохраненный QR код: {len(saved_qr)} bytes")
    except RedisError as e:
        print(f"[ERROR] Ошибка сохранения QR кода в Redis: {str(e)}")
        raise
    except Exception as e:
        print(f"[ERROR] Неожиданная ошибка при работе с Redis: {str(e)}")
        raise

async def delete_qr_code(account_id: str) -> None:
    """Удаляет QR-код из Redis"""
    key = f"whatsapp:qr:{account_id}"
    try:
        # Проверяем подключение
        await redis.ping()
        print("[DEBUG] Redis подключение активно")
        
        print(f"[DEBUG] Redis DELETE {key}")
        await redis.delete(key)
    except RedisError as e:
        print(f"[ERROR] Ошибка удаления QR кода из Redis: {str(e)}")
        raise
    except Exception as e:
        print(f"[ERROR] Неожиданная ошибка при работе с Redis: {str(e)}")
        raise