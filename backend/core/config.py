from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://loanuser:loanpass@postgres:5432/loandb"
    redis_url: str = "redis://:redispass@redis:6379/0"
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen3:latest"
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
    # LLM provider: "ollama" (local) or "claude" (cloud)
    llm_provider: str = "ollama"
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"
    langfuse_public_key: str = "pk-lf-loan-intake-key"
    langfuse_secret_key: str = "sk-lf-loan-intake-key"
    langfuse_host: str = "http://langfuse:3000"

    class Config:
        env_file = ".env"
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
