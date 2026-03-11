from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from api.chat import router as chat_router
from api.application import router as app_router
from api.upload import router as upload_router
from db.session import init_db
from core.redis_client import init_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Loan Intake Agent backend...")
    await init_db()
    await init_redis()
    logger.info("✅ Database and Redis ready")
    yield
    logger.info("👋 Shutting down...")

app = FastAPI(
    title="Loan Intake Agent API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router,   prefix="/api/chat",        tags=["Chat"])
app.include_router(app_router,    prefix="/api/application",  tags=["Application"])
app.include_router(upload_router, prefix="/api/upload",       tags=["Documents"])

@app.get("/health")
async def health():
    return {"status": "ok", "service": "backend"}

@app.post("/api/internal/kong-logs")
async def kong_logs(payload: dict):
    return {"received": True}
