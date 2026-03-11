# ============================================================
# mock-hub/docusign.py — Document Signing
# ============================================================
import uuid, random
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class EnvelopeRequest(BaseModel):
    applicant_name: str
    applicant_email: str
    application_number: str
    loan_amount: float
    loan_term_months: int
    interest_rate: float
    monthly_payment: float
    document_type: str = "LOAN_AGREEMENT"

class EnvelopeResponse(BaseModel):
    envelope_id: str
    status: str
    signing_url: str
    expires_at: str
    document_name: str
    timestamp: str

class SigningStatusResponse(BaseModel):
    envelope_id: str
    status: str             # SENT, DELIVERED, COMPLETED, DECLINED, VOIDED
    signed_at: Optional[str]
    document_url: Optional[str]
    timestamp: str

class WebhookSimulateRequest(BaseModel):
    envelope_id: str
    outcome: str = "COMPLETED"  # COMPLETED or DECLINED

# Store envelopes in memory for demo
_envelopes: dict = {}

@router.post("/create-envelope", response_model=EnvelopeResponse)
async def create_envelope(req: EnvelopeRequest):
    env_id = f"ENV-{uuid.uuid4().hex[:16].upper()}"
    expires = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()

    # Signing URL — in real DocuSign this redirects to their UI
    signing_url = f"http://localhost:9000/docusign/sign/{env_id}?name={req.applicant_name.replace(' ', '+')}&email={req.applicant_email}"

    _envelopes[env_id] = {
        "status":       "SENT",
        "applicant":    req.applicant_name,
        "email":        req.applicant_email,
        "app_number":   req.application_number,
        "loan_amount":  req.loan_amount,
        "signed_at":    None,
        "created_at":   datetime.now(timezone.utc).isoformat()
    }

    return EnvelopeResponse(
        envelope_id  = env_id,
        status       = "SENT",
        signing_url  = signing_url,
        expires_at   = expires,
        document_name = f"Loan_Agreement_{req.application_number}.pdf",
        timestamp    = datetime.now(timezone.utc).isoformat()
    )

@router.get("/envelope/{envelope_id}/status", response_model=SigningStatusResponse)
async def get_envelope_status(envelope_id: str):
    env = _envelopes.get(envelope_id)
    if not env:
        return SigningStatusResponse(
            envelope_id  = envelope_id,
            status       = "NOT_FOUND",
            signed_at    = None,
            document_url = None,
            timestamp    = datetime.now(timezone.utc).isoformat()
        )
    return SigningStatusResponse(
        envelope_id  = envelope_id,
        status       = env["status"],
        signed_at    = env.get("signed_at"),
        document_url = f"http://localhost:9000/docusign/documents/{envelope_id}.pdf" if env["status"] == "COMPLETED" else None,
        timestamp    = datetime.now(timezone.utc).isoformat()
    )

@router.get("/sign/{envelope_id}")
async def signing_page(envelope_id: str, name: str = "", email: str = ""):
    """Simulated signing page — auto-completes for demo."""
    if envelope_id in _envelopes:
        _envelopes[envelope_id]["status"]    = "COMPLETED"
        _envelopes[envelope_id]["signed_at"] = datetime.now(timezone.utc).isoformat()
    return {
        "message":     "Document signed successfully (mock)",
        "envelope_id": envelope_id,
        "signer":      name,
        "status":      "COMPLETED",
        "next":        "You may close this window and return to the application."
    }

@router.post("/webhook/simulate")
async def simulate_webhook(req: WebhookSimulateRequest):
    """Manually trigger a DocuSign webhook event for testing."""
    if req.envelope_id in _envelopes:
        _envelopes[req.envelope_id]["status"] = req.outcome
        if req.outcome == "COMPLETED":
            _envelopes[req.envelope_id]["signed_at"] = datetime.now(timezone.utc).isoformat()
    return {"envelope_id": req.envelope_id, "simulated_status": req.outcome}


