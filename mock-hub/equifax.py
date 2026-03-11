"""
Mock Equifax — Credit Report
Returns realistic credit report data including score, tradelines,
derogatory marks, and debt-to-income inputs.
"""
import random
import uuid
from datetime import datetime, timezone, date, timedelta
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

# ── Models ───────────────────────────────────────────────────

class CreditReportRequest(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: str
    ssn_last_four: str
    street_address: str
    zip_code: str
    loan_amount_requested: float

class Tradeline(BaseModel):
    creditor: str
    account_type: str
    balance: float
    credit_limit: float
    monthly_payment: float
    payment_status: str
    months_open: int
    derogatory: bool

class CreditReportResponse(BaseModel):
    reference_id: str
    credit_score: int
    score_model: str
    risk_grade: str
    total_accounts: int
    open_accounts: int
    derogatory_marks: int
    total_balance: float
    total_monthly_payments: float
    available_credit: float
    credit_utilization_pct: float
    oldest_account_years: float
    inquiries_last_6mo: int
    public_records: int
    tradelines: list
    factors: list
    pull_type: str
    timestamp: str

# ── Helpers ──────────────────────────────────────────────────

CREDITORS = [
    ("Chase Sapphire",      "Credit Card",    15000),
    ("Bank of America",     "Credit Card",    8000),
    ("Wells Fargo",         "Auto Loan",      0),
    ("Sallie Mae",          "Student Loan",   0),
    ("Capital One",         "Credit Card",    5000),
    ("Discover",            "Credit Card",    6000),
    ("Citi",                "Personal Loan",  0),
    ("TD Bank",             "Mortgage",       0),
    ("Navient",             "Student Loan",   0),
    ("American Express",    "Credit Card",    20000),
]

def _score_band(ssn_last: str) -> tuple:
    """Deterministic score range based on SSN last 4 for demo consistency."""
    seed = int(ssn_last) if ssn_last.isdigit() else 650
    if seed < 1000:   # always true — just spread the range
        if seed % 5 == 0:   return (750, 800, "A", "Excellent")
        if seed % 5 == 1:   return (700, 749, "B", "Good")
        if seed % 5 == 2:   return (660, 699, "C", "Fair")
        if seed % 5 == 3:   return (620, 659, "D", "Poor")
        return               (550, 619, "F", "Very Poor")
    return (680, 720, "B", "Good")

def _build_tradelines(score: int) -> list:
    num = random.randint(3, 8)
    tradelines = []
    for creditor, acct_type, limit in random.sample(CREDITORS, min(num, len(CREDITORS))):
        derog = score < 620 and random.random() < 0.3
        balance = round(random.uniform(0.1, 0.85) * limit, 2) if limit > 0 else round(random.uniform(5000, 25000), 2)
        payment = round(balance * 0.02 if acct_type == "Credit Card" else balance / random.randint(24, 60), 2)
        tradelines.append({
            "creditor":       creditor,
            "account_type":   acct_type,
            "balance":        balance,
            "credit_limit":   limit,
            "monthly_payment": payment,
            "payment_status": "DEROGATORY" if derog else "CURRENT",
            "months_open":    random.randint(6, 120),
            "derogatory":     derog
        })
    return tradelines

# ── Endpoint ─────────────────────────────────────────────────

@router.post("/credit-report", response_model=CreditReportResponse)
async def get_credit_report(req: CreditReportRequest):
    low, high, grade, label = _score_band(req.ssn_last_four)
    score = random.randint(low, high)
    tradelines = _build_tradelines(score)

    total_balance   = sum(t["balance"] for t in tradelines)
    total_limit     = sum(t["credit_limit"] for t in tradelines if t["credit_limit"] > 0)
    total_payments  = sum(t["monthly_payment"] for t in tradelines)
    derog_count     = sum(1 for t in tradelines if t["derogatory"])
    utilization     = round((total_balance / total_limit * 100) if total_limit > 0 else 0, 1)

    # Score-based factors
    factors = []
    if utilization > 30:   factors.append("HIGH_CREDIT_UTILIZATION")
    if derog_count > 0:    factors.append("DEROGATORY_MARKS_PRESENT")
    if score < 660:        factors.append("LIMITED_CREDIT_HISTORY")
    if score >= 720:       factors.append("EXCELLENT_PAYMENT_HISTORY")
    if not factors:        factors.append("GOOD_CREDIT_MIX")

    return CreditReportResponse(
        reference_id        = f"EFX-{uuid.uuid4().hex[:10].upper()}",
        credit_score        = score,
        score_model         = "Equifax Credit Score 3.0",
        risk_grade          = grade,
        total_accounts      = len(tradelines),
        open_accounts       = len(tradelines) - random.randint(0, 2),
        derogatory_marks    = derog_count,
        total_balance       = round(total_balance, 2),
        total_monthly_payments = round(total_payments, 2),
        available_credit    = round(total_limit - total_balance, 2),
        credit_utilization_pct = utilization,
        oldest_account_years = round(random.uniform(1.5, 12.0), 1),
        inquiries_last_6mo  = random.randint(0, 4),
        public_records      = 1 if score < 580 else 0,
        tradelines          = tradelines,
        factors             = factors,
        pull_type           = "SOFT",
        timestamp           = datetime.now(timezone.utc).isoformat()
    )
