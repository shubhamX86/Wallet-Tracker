"""Redis client and connectivity probe."""
import redis.asyncio as aioredis

from app.core.config import get_settings

redis_client = aioredis.from_url(get_settings().redis_url, decode_responses=True)


async def check_redis() -> bool:
    try:
        return bool(await redis_client.ping())
    except Exception:
        return False
