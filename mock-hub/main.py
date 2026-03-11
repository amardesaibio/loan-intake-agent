from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
import json
import time

from socure import router as socure_router
from equifax import router as equifax_router
from plaid import router as plaid_router
from argyle import router as argyle_router
from docusign import router as docusign_router
from email_service import router as email_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mock-hub")

app = FastAPI(
    title="Mock Integration Hub",
    description="Realistic mock endpoints for Socure, Equifax, Plaid, Argyle, DocuSign, Email",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    # Log request body for POST calls
    if request.method == "POST":
        body_bytes = await request.body()
        try:
            body = json.loads(body_bytes)
            logger.info(f">>> {request.method} {request.url.path} REQUEST: {json.dumps(body, indent=2)}")
        except Exception:
            logger.info(f">>> {request.method} {request.url.path} REQUEST: (non-JSON body)")
        # Reconstruct body so the endpoint can still read it
        from starlette.requests import Request as StarletteRequest
        import io
        request._body = body_bytes

    response = await call_next(request)

    # Capture and log response body
    from starlette.responses import Response
    resp_body = b""
    async for chunk in response.body_iterator:
        resp_body += chunk
    elapsed = round((time.time() - start) * 1000)
    try:
        resp_json = json.loads(resp_body)
        logger.info(f"<<< {request.url.path} RESPONSE [{response.status_code}] ({elapsed}ms): {json.dumps(resp_json, indent=2)}")
    except Exception:
        logger.info(f"<<< {request.url.path} RESPONSE [{response.status_code}] ({elapsed}ms)")

    return Response(
        content=resp_body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
    )

app.include_router(socure_router,   prefix="/socure",   tags=["Socure — ID Verification"])
app.include_router(equifax_router,  prefix="/equifax",  tags=["Equifax — Credit Check"])
app.include_router(plaid_router,    prefix="/plaid",    tags=["Plaid — Income Verification"])
app.include_router(argyle_router,   prefix="/argyle",   tags=["Argyle — Employment Verification"])
app.include_router(docusign_router, prefix="/docusign", tags=["DocuSign — Document Signing"])
app.include_router(email_router,    prefix="/email",    tags=["Email — Notifications"])

@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-hub", "integrations": [
        "socure", "equifax", "plaid", "argyle", "docusign", "email"
    ]}

@app.get("/")
async def root():
    return {
        "message": "Mock Integration Hub",
        "docs": "/docs",
        "endpoints": {
            "socure":   "/socure/verify-identity",
            "equifax":  "/equifax/credit-report",
            "plaid":    "/plaid/income-report",
            "argyle":   "/argyle/employment-record",
            "docusign": "/docusign/create-envelope",
            "email":    "/email/send"
        }
    }
