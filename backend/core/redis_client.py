import redis.asyncio as aioredis
import json
import logging
from typing import Optional
from core.config import get_settings

logger = logging.getLogger(__name__)
_redis = None
SESSION_TTL = 60 * 60 * 4

async def init_redis():
    global _redis
    settings = get_settings()
    _redis = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    await _redis.ping()
    logger.info("✅ Redis connected")

def get_redis():
    if _redis is None:
        raise RuntimeError("Redis not initialised")
    return _redis

async def get_session(session_id: str) -> Optional[dict]:
    r = get_redis()
    raw = await r.get(f"session:{session_id}")
    return json.loads(raw) if raw else None

async def set_session(session_id: str, data: dict):
    r = get_redis()
    await r.setex(f"session:{session_id}", SESSION_TTL, json.dumps(data))

async def update_session(session_id: str, updates: dict):
    existing = await get_session(session_id) or {}
    existing.update(updates)
    await set_session(session_id, existing)

async def delete_session(session_id: str):
    r = get_redis()
    await r.delete(f"session:{session_id}")

async def append_message(session_id: str, role: str, content: str, metadata: dict = None):
    r = get_redis()
    key = f"history:{session_id}"
    msg = {"role": role, "content": content}
    if metadata:
        msg["metadata"] = metadata
    await r.rpush(key, json.dumps(msg))
    await r.expire(key, SESSION_TTL)

async def get_history(session_id: str) -> list:
    r = get_redis()
    raw = await r.lrange(f"history:{session_id}", 0, -1)
    return [json.loads(m) for m in raw]
