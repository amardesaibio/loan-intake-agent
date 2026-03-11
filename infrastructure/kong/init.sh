#!/bin/sh
# Kong route initialisation — runs once after Kong is healthy

KONG_ADMIN="http://kong:8001"

echo "⏳ Waiting for Kong admin API..."
until curl -sf "$KONG_ADMIN/status" > /dev/null; do
  sleep 2
done
echo "✅ Kong is ready"

# ── Services ─────────────────────────────────────────────────

# Backend service
curl -sf -X POST "$KONG_ADMIN/services" \
  -d name=backend \
  -d url=http://backend:8080 \
  > /dev/null && echo "✅ Backend service registered"

# Mock hub service
curl -sf -X POST "$KONG_ADMIN/services" \
  -d name=mock-hub \
  -d url=http://mock-hub:9000 \
  > /dev/null && echo "✅ Mock hub service registered"

# ── Routes ───────────────────────────────────────────────────

# Backend routes — all /api/* traffic
curl -sf -X POST "$KONG_ADMIN/services/backend/routes" \
  -d "name=backend-api" \
  -d "paths[]=/api" \
  -d "strip_path=false" \
  > /dev/null && echo "✅ Backend route /api registered"

# Mock hub routes — /mock/* (for testing/demo purposes)
curl -sf -X POST "$KONG_ADMIN/services/mock-hub/routes" \
  -d "name=mock-hub-api" \
  -d "paths[]=/mock" \
  -d "strip_path=true" \
  > /dev/null && echo "✅ Mock hub route /mock registered"

# ── Plugins ──────────────────────────────────────────────────

# Rate limiting on backend
curl -sf -X POST "$KONG_ADMIN/services/backend/plugins" \
  -d "name=rate-limiting" \
  -d "config.minute=60" \
  -d "config.hour=1000" \
  -d "config.policy=local" \
  > /dev/null && echo "✅ Rate limiting plugin applied"

# Request size limit (for document uploads — 20MB)
curl -sf -X POST "$KONG_ADMIN/services/backend/plugins" \
  -d "name=request-size-limiting" \
  -d "config.allowed_payload_size=20" \
  > /dev/null && echo "✅ Request size limiting applied (20MB)"

# CORS plugin
curl -sf -X POST "$KONG_ADMIN/services/backend/plugins" \
  -d "name=cors" \
  -d "config.origins[]=http://localhost:3000" \
  -d "config.methods[]=GET" \
  -d "config.methods[]=POST" \
  -d "config.methods[]=PUT" \
  -d "config.methods[]=DELETE" \
  -d "config.methods[]=OPTIONS" \
  -d "config.headers[]=Authorization" \
  -d "config.headers[]=Content-Type" \
  -d "config.credentials=true" \
  > /dev/null && echo "✅ CORS plugin applied"

# Request logging
curl -sf -X POST "$KONG_ADMIN/services/backend/plugins" \
  -d "name=http-log" \
  -d "config.http_endpoint=http://backend:8080/api/internal/kong-logs" \
  -d "config.method=POST" \
  -d "config.timeout=1000" \
  -d "config.keepalive=1000" \
  > /dev/null && echo "✅ HTTP logging plugin applied"

echo ""
echo "🎉 Kong initialisation complete"
echo "   Proxy:  http://localhost:8000"
echo "   Admin:  http://localhost:8001"
