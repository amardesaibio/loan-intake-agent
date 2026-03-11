#!/bin/bash
# Run from loan-intake-agent/ root
set -e
echo "📁 Creating missing API stubs..."

# ── api/application.py ───────────────────────────────────────
cat > backend/api/application.py << 'PYEOF'
from fastapi import APIRouter
router = APIRouter()

@router.get("/status/{session_id}")
async def get_application_status(session_id: str):
    return {"session_id": session_id, "status": "in_progress"}
PYEOF
echo "✅ api/application.py"

# ── api/upload.py ────────────────────────────────────────────
cat > backend/api/upload.py << 'PYEOF'
from fastapi import APIRouter
router = APIRouter()

@router.post("/document")
async def upload_document():
    return {"status": "upload endpoint coming soon"}
PYEOF
echo "✅ api/upload.py"

# ── core/config.py — ensure it exists as a standalone file ───
mkdir -p backend/core
cat > backend/core/__init__.py << 'PYEOF'
PYEOF

cat > backend/core/config.py << 'PYEOF'
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://loanuser:loanpass@postgres:5432/loandb"
    redis_url: str = "redis://:redispass@redis:6379/0"
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_embed_model: str = "nomic-embed-text:latest"
    ollama_fallback_model: str = "llama3.1:latest"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120
    mock_hub_url: str = "http://mock-hub:9000"
    upload_dir: str = "/app/uploads"
    max_upload_size_mb: int = 20
    environment: str = "development"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
PYEOF
echo "✅ core/config.py"

# ── core/redis_client.py ─────────────────────────────────────
cat > backend/core/redis_client.py << 'PYEOF'
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
PYEOF
echo "✅ core/redis_client.py"

# ── db/session.py ────────────────────────────────────────────
mkdir -p backend/db
cat > backend/db/__init__.py << 'PYEOF'
PYEOF

cat > backend/db/session.py << 'PYEOF'
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import logging
from core.config import get_settings

logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

_engine = None
_session_factory = None

async def init_db():
    global _engine, _session_factory
    settings = get_settings()
    _engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=10,
        max_overflow=20
    )
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    logger.info("✅ Database engine created")

def get_session_factory():
    if _session_factory is None:
        raise RuntimeError("DB not initialised")
    return _session_factory

async def get_db():
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
PYEOF
echo "✅ db/session.py"

# ── Ensure all __init__.py exist ─────────────────────────────
for d in backend backend/api backend/agent backend/agent/stages backend/db backend/core backend/integrations backend/services backend/middleware; do
    mkdir -p $d
    touch $d/__init__.py
done
echo "✅ All __init__.py files in place"

echo ""
echo "🎉 Done! Now run:"
echo "   docker compose build backend && docker compose up -d backend"
echo "   docker compose logs backend -f --tail=40"
