# ============================================================
# mock-hub/argyle.py — Employment Verification
# ============================================================
# Save this section as a separate argyle.py file

"""
Mock Argyle — Employment & Payroll Verification
"""
from fastapi import APIRouter as ArgyleRouter
from pydantic import BaseModel as ArgyleBase
import random, uuid
from datetime import datetime, timezone

argyle_router = ArgyleRouter()

class ArgyleEmploymentRequest(ArgyleBase):
    applicant_name: str
    employer_name: str
    job_title: str
    stated_annual_salary: float
    stated_years_employed: float

class ArgyleEmploymentResponse(ArgyleBase):
    reference_id: str
    employer_verified: bool
    employer_name: str
    employer_address: str
    employment_status: str
    job_title_verified: str
    employment_type: str
    start_date: str
    tenure_months: int
    verified_annual_salary: float
    pay_frequency: str
    last_pay_date: str
    ytd_earnings: float
    salary_match_pct: float
    timestamp: str

@argyle_router.post("/employment-record")
async def get_employment_record(req: ArgyleEmploymentRequest):
    variance     = random.uniform(-0.08, 0.08)
    verified_sal = round(req.stated_annual_salary * (1 + variance), 2)
    match_pct    = round((1 - abs(variance)) * 100, 1)
    tenure       = max(1, int(req.stated_years_employed * 12) + random.randint(-2, 2))

    today = datetime.now(timezone.utc)
    start_year = today.year - int(tenure / 12)

    return ArgyleEmploymentResponse(
        reference_id            = f"ARGYLE-{uuid.uuid4().hex[:10].upper()}",
        employer_verified       = True,
        employer_name           = req.employer_name,
        employer_address        = f"{random.randint(100,9999)} Business Ave, {random.choice(['New York, NY', 'Chicago, IL', 'Austin, TX', 'Seattle, WA', 'Boston, MA'])} {random.randint(10000,99999)}",
        employment_status       = "ACTIVE",
        job_title_verified      = req.job_title,
        employment_type         = random.choice(["FULL_TIME", "FULL_TIME", "FULL_TIME", "PART_TIME"]),
        start_date              = f"{start_year}-{random.randint(1,12):02d}-01",
        tenure_months           = tenure,
        verified_annual_salary  = verified_sal,
        pay_frequency           = "BIWEEKLY",
        last_pay_date           = (today - timedelta(days=random.randint(1, 14))).strftime("%Y-%m-%d"),
        ytd_earnings            = round(verified_sal * (today.month / 12), 2),
        salary_match_pct        = match_pct,
        timestamp               = today.isoformat()
    )

# Make argyle router importable as `router`
router = argyle_router
