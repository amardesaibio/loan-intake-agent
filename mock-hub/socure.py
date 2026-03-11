"""
Mock Socure — Identity Verification
Realistic responses based on name/SSN patterns for demo purposes.
"""
import random
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

# ── Request / Response Models ────────────────────────────────

class IdentityVerifyRequest(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: str          # YYYY-MM-DD
    ssn_last_four: str
    email: str
    phone: str
    street_address: str
    city: str
    state: str
    zip_code: str

class IdentityVerifyResponse(BaseModel):
    reference_id: str
    status: str                 # PASS, FAIL, REVIEW
    score: float                # 0.0 – 1.0
    kyc_result: dict
    fraud_result: dict
    address_result: dict
    reasons: list
    timestamp: str

# ── Outcome logic ────────────────────────────────────────────

def _determine_outcome(req: IdentityVerifyRequest):
    """
    Simulate realistic outcomes:
    - SSN ending 0000        → FAIL (known fraud pattern)
    - SSN ending 9999        → REVIEW (thin file)
    - Everything else        → PASS (weighted 85% pass)
    """
    if req.ssn_last_four == "0000":
        return "FAIL", 0.08
    if req.ssn_last_four == "9999":
        return "REVIEW", 0.52
    # 85% pass, 5% review, 10% fail for random
    roll = random.random()
    if roll < 0.85:
        return "PASS", round(random.uniform(0.82, 0.99), 2)
    elif roll < 0.90:
        return "REVIEW", round(random.uniform(0.45, 0.65), 2)
    else:
        return "FAIL", round(random.uniform(0.05, 0.25), 2)

# ── Endpoint ─────────────────────────────────────────────────

@router.post("/verify-identity", response_model=IdentityVerifyResponse)
async def verify_identity(req: IdentityVerifyRequest):
    status, score = _determine_outcome(req)
    ref_id = f"SOCURE-{uuid.uuid4().hex[:12].upper()}"

    kyc_result = {
        "name_match":       status != "FAIL",
        "dob_match":        status != "FAIL",
        "ssn_match":        status == "PASS",
        "address_verified": status == "PASS",
        "kyc_score":        score
    }

    fraud_result = {
        "fraud_score":          round(1 - score, 2),
        "synthetic_identity":   status == "FAIL",
        "velocity_abuse":       False,
        "device_risk":          "LOW" if status == "PASS" else "HIGH",
        "email_risk":           "LOW" if status == "PASS" else "MEDIUM",
        "phone_risk":           "LOW"
    }

    address_result = {
        "deliverable":          True,
        "residential":          True,
        "po_box":               False,
        "high_risk_address":    status == "FAIL",
        "years_at_address":     random.randint(1, 8)
    }

    reasons = []
    if status == "FAIL":
        reasons = ["SSN_NOT_FOUND", "IDENTITY_NOT_VERIFIED", "HIGH_FRAUD_RISK"]
    elif status == "REVIEW":
        reasons = ["THIN_FILE", "ADDRESS_MISMATCH_MINOR", "MANUAL_REVIEW_REQUIRED"]
    else:
        reasons = ["IDENTITY_VERIFIED", "LOW_FRAUD_RISK"]

    return IdentityVerifyResponse(
        reference_id=ref_id,
        status=status,
        score=score,
        kyc_result=kyc_result,
        fraud_result=fraud_result,
        address_result=address_result,
        reasons=reasons,
        timestamp=datetime.now(timezone.utc).isoformat()
    )

@router.get("/verify-identity/{reference_id}")
async def get_verification_result(reference_id: str):
    """Check status of a previous verification (webhook alternative)."""
    return {
        "reference_id": reference_id,
        "status": "PASS",
        "message": "Verification complete"
    }
