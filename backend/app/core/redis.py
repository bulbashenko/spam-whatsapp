from redis import asyncio as aioredis
from redis.exceptions import RedisError
from app.core.config import settings
import json
from typing import Optional, Dict, List, Any
from datetime import datetime


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
    key = f"whatsapp:qr:{account_id}"
    try:
        await redis.ping()
        
        qr_code = await redis.get(key)
        return qr_code
    except RedisError as e:
        return None
    except Exception as e:
        return None

async def set_qr_code(account_id: str, qr_code: str, expire: int = 120) -> None:
    key = f"whatsapp:qr:{account_id}"
    try:
        await redis.ping()
        await redis.set(key, qr_code, ex=expire)  # Expire через 5 минут
        
        # Проверяем, что QR код действительно сохранился
        saved_qr = await redis.get(key)

    except RedisError as e:
        raise
    except Exception as e:
        raise

async def delete_qr_code(account_id: str) -> None:
    key = f"whatsapp:qr:{account_id}"
    try:
        await redis.delete(key)
    except Exception as e:
        raise

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