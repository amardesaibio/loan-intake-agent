#!/bin/bash
# ============================================================
# Loan Intake Agent — Local Setup Script
# Run once to bootstrap everything
# ============================================================

set -e
echo ""
echo "🏦 Loan Intake Agent — Setup"
echo "================================"

# ── Check prerequisites ───────────────────────────────────────
echo ""
echo "📋 Checking prerequisites..."

command -v docker >/dev/null 2>&1 || { echo "❌ Docker not found. Install Docker Desktop first."; exit 1; }
command -v docker-compose >/dev/null 2>&1 || command -v "docker compose" >/dev/null 2>&1 || { echo "❌ Docker Compose not found."; exit 1; }

echo "✅ Docker found: $(docker --version)"

# ── Create .env ───────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  echo "✅ .env created from .env.example"
else
  echo "ℹ️  .env already exists, skipping"
fi

# ── Create folder structure ───────────────────────────────────
echo ""
echo "📁 Creating project structure..."

mkdir -p backend/api
mkdir -p backend/agent/stages
mkdir -p backend/agent/prompts
mkdir -p backend/integrations
mkdir -p backend/models
mkdir -p backend/services
mkdir -p backend/middleware
mkdir -p mock-hub
mkdir -p frontend/src/components
mkdir -p frontend/src/hooks
mkdir -p infrastructure/postgres
mkdir -p infrastructure/kong
mkdir -p uploads

echo "✅ Folder structure created"

# ── Placeholder Dockerfiles ───────────────────────────────────
echo ""
echo "🐳 Creating placeholder Dockerfiles..."

# Backend Dockerfile
if [ ! -f backend/Dockerfile ]; then
cat > backend/Dockerfile << 'EOF'
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]
EOF
echo "✅ backend/Dockerfile created"
fi

# Backend requirements.txt placeholder
if [ ! -f backend/requirements.txt ]; then
cat > backend/requirements.txt << 'EOF'
fastapi==0.115.0
uvicorn[standard]==0.31.0
asyncpg==0.29.0
sqlalchemy[asyncio]==2.0.35
alembic==1.13.3
redis[asyncio]==5.1.1
python-jose[cryptography]==3.3.0
python-multipart==0.0.12
httpx==0.27.2
pydantic==2.9.2
pydantic-settings==2.5.2
langgraph==0.2.28
langchain==0.3.4
langchain-community==0.3.3
langchain-ollama==0.2.0
pymupdf==1.24.11
pytesseract==0.3.13
pillow==11.0.0
python-dotenv==1.0.1
aiosmtplib==3.0.2
email-validator==2.2.0
EOF
echo "✅ backend/requirements.txt created"
fi

# Backend main.py placeholder
if [ ! -f backend/main.py ]; then
cat > backend/main.py << 'EOF'
from fastapi import FastAPI

app = FastAPI(title="Loan Intake Agent API")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "backend"}

@app.post("/api/internal/kong-logs")
async def kong_logs(payload: dict):
    return {"received": True}
EOF
echo "✅ backend/main.py placeholder created"
fi

# Mock Hub Dockerfile
if [ ! -f mock-hub/Dockerfile ]; then
cat > mock-hub/Dockerfile << 'EOF'
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000", "--reload"]
EOF
echo "✅ mock-hub/Dockerfile created"
fi

# Mock Hub requirements.txt
if [ ! -f mock-hub/requirements.txt ]; then
cat > mock-hub/requirements.txt << 'EOF'
fastapi==0.115.0
uvicorn[standard]==0.31.0
httpx==0.27.2
aiosmtplib==3.0.2
faker==30.3.0
python-dotenv==1.0.1
EOF
echo "✅ mock-hub/requirements.txt created"
fi

# Mock Hub main.py placeholder
if [ ! -f mock-hub/main.py ]; then
cat > mock-hub/main.py << 'EOF'
from fastapi import FastAPI

app = FastAPI(title="Mock Integration Hub")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-hub"}
EOF
echo "✅ mock-hub/main.py placeholder created"
fi

# Frontend Dockerfile
if [ ! -f frontend/Dockerfile ]; then
cat > frontend/Dockerfile << 'EOF'
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
EOF
echo "✅ frontend/Dockerfile created"
fi

# Frontend package.json placeholder
if [ ! -f frontend/package.json ]; then
cat > frontend/package.json << 'EOF'
{
  "name": "loan-intake-agent-frontend",
  "version": "0.0.1",
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.2",
    "vite": "^5.4.8",
    "tailwindcss": "^3.4.14",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.47"
  }
}
EOF
echo "✅ frontend/package.json created"
fi

# ── Pull Ollama model ─────────────────────────────────────────
echo ""
echo "🤖 Note: After Docker starts, pull your LLM model:"
echo "   docker exec loan-ollama ollama pull llama3.1:8b"
echo "   (or: mistral:7b / llama3.2:3b for lighter models)"

# ── Start Docker Compose ──────────────────────────────────────
echo ""
echo "🚀 Starting all services..."
docker compose up -d --build

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 15

# ── Status check ──────────────────────────────────────────────
echo ""
echo "📊 Service Status:"
docker compose ps

echo ""
echo "================================"
echo "🎉 Setup Complete!"
echo "================================"
echo ""
echo "📌 Service URLs:"
echo "   Frontend:          http://localhost:3000"
echo "   Backend API:       http://localhost:8080"
echo "   Kong Proxy:        http://localhost:8000"
echo "   Kong Admin:        http://localhost:8001"
echo "   Mock Hub:          http://localhost:9000"
echo "   Ollama:            http://localhost:11434"
echo "   MailHog (email):   http://localhost:8025"
echo "   PostgreSQL:        localhost:5432"
echo "   Redis:             localhost:6379"
echo ""
echo "📌 Next step — pull your LLM:"
echo "   docker exec loan-ollama ollama pull llama3.1:8b"
echo ""
