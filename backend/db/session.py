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
