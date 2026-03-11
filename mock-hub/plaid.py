# ============================================================
# mock-hub/plaid.py — Income & Bank Verification
# ============================================================
import random, uuid
from datetime import datetime, timezone, date, timedelta
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class PlaidIncomeRequest(BaseModel):
    applicant_name: str
    stated_annual_income: float
    employer_name: str

class PlaidIncomeResponse(BaseModel):
    reference_id: str
    verified: bool
    verified_annual_income: float
    verified_monthly_income: float
    income_stability_score: float   # 0–1
    income_match_pct: float         # how close to stated income
    bank_accounts: list
    avg_monthly_deposits: float
    avg_monthly_balance: float
    nsf_count_last_90d: int         # non-sufficient funds
    income_sources: list
    timestamp: str

def _gen_accounts(monthly_income: float) -> list:
    accounts = []
    types = [("Checking", "CHECKING"), ("Savings", "SAVINGS")]
    for name, atype in random.sample(types, k=random.randint(1, 2)):
        balance = round(random.uniform(0.5, 4.0) * monthly_income, 2)
        accounts.append({
            "account_id":   f"acct_{uuid.uuid4().hex[:8]}",
            "name":         f"{name} ••••{random.randint(1000,9999)}",
            "type":         atype,
            "balance":      balance,
            "institution":  random.choice(["Chase", "Bank of America", "Wells Fargo", "TD Bank", "Citi"])
        })
    return accounts

@router.post("/income-report", response_model=PlaidIncomeResponse)
async def get_income_report(req: PlaidIncomeRequest):
    # Verify within ±15% of stated income
    variance = random.uniform(-0.15, 0.15)
    verified_annual = round(req.stated_annual_income * (1 + variance), 2)
    verified_monthly = round(verified_annual / 12, 2)
    match_pct = round((1 - abs(variance)) * 100, 1)
    stability = round(random.uniform(0.70, 0.98), 2)
    accounts = _gen_accounts(verified_monthly)

    return PlaidIncomeResponse(
        reference_id            = f"PLAID-{uuid.uuid4().hex[:10].upper()}",
        verified                = abs(variance) < 0.12,
        verified_annual_income  = verified_annual,
        verified_monthly_income = verified_monthly,
        income_stability_score  = stability,
        income_match_pct        = match_pct,
        bank_accounts           = accounts,
        avg_monthly_deposits    = round(verified_monthly * random.uniform(1.0, 1.2), 2),
        avg_monthly_balance     = round(verified_monthly * random.uniform(0.8, 2.5), 2),
        nsf_count_last_90d      = random.choices([0, 1, 2, 3], weights=[70, 15, 10, 5])[0],
        income_sources          = [{
            "source":       req.employer_name or "Primary Employer",
            "type":         "SALARY",
            "amount":       verified_monthly,
            "frequency":    "BIWEEKLY",
            "confidence":   stability
        }],
        timestamp               = datetime.now(timezone.utc).isoformat()
    )


