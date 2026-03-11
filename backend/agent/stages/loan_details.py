# ============================================================
# backend/agent/stages/loan_details.py
# ============================================================
import json, logging, httpx
from langchain_core.messages import AIMessage, HumanMessage
from agent.state import LoanAgentState
from core.config import get_settings

logger = logging.getLogger(__name__)

LOAN_PURPOSES = {
    "debt": "debt_consolidation", "consolidat": "debt_consolidation",
    "home": "home_improvement", "renovati": "home_improvement", "repair": "home_improvement",
    "medical": "medical", "health": "medical",
    "car": "vehicle", "vehicle": "vehicle", "auto": "vehicle",
    "education": "education", "school": "education",
    "vacation": "vacation", "travel": "vacation",
    "wedding": "wedding",
    "business": "business",
}

TERM_OPTIONS = {12: 12, 24: 24, 36: 36, 48: 48, 60: 60}

# Interest rate tiers (will be refined by credit score in decision stage)
RATE_TIERS = {
    "excellent": 7.99,  # 720+
    "good":      11.99, # 680-719
    "fair":      16.99, # 640-679
    "poor":      22.99  # below 640
}

LOAN_QUESTIONS = {
    "loan_amount":       "**How much would you like to borrow?** (between $1,000 and $50,000)",
    "loan_purpose":      "What will you be using the loan for? (e.g. debt consolidation, home improvement, medical, vehicle, vacation, other)",
    "loan_term_months":  "How long would you like to repay it? We offer terms of **12, 24, 36, 48, or 60 months**. Which works best for you?",
}

async def _extract_loan(msg: str, current: dict) -> dict:
    settings = get_settings()
    prompt = f"""Extract loan request information from: "{msg}"
Return ONLY JSON with any found:
- loan_amount (float, convert "$25k" -> 25000.0)
- loan_purpose (one of: debt_consolidation, home_improvement, medical, vehicle, education, vacation, wedding, business, other)
- loan_term_months (integer, one of: 12, 24, 36, 48, 60 — pick closest if they say "3 years" -> 36, "5 years" -> 60)
Return {{}} if nothing found."""
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{settings.ollama_base_url}/api/generate",
            json={"model": settings.ollama_model, "prompt": prompt + " /no_think",
                  "stream": False, "options": {"temperature": 0.1, "num_predict": 4096}})
        text = r.json().get("response", "{}")
    try:
        s, e = text.find("{"), text.rfind("}") + 1
        return json.loads(text[s:e]) if s >= 0 else {}
    except Exception:
        return {}

def _estimate_payment(amount: float, term: int, rate_pct: float = 14.99) -> float:
    """Calculate estimated monthly payment."""
    monthly_rate = rate_pct / 100 / 12
    if monthly_rate == 0:
        return round(amount / term, 2)
    payment = amount * (monthly_rate * (1 + monthly_rate)**term) / ((1 + monthly_rate)**term - 1)
    return round(payment, 2)

async def loan_details_node(state: LoanAgentState) -> dict:
    messages = state.get("messages", [])
    app_data = state.get("applicant_data", {})

    last_msg = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    if last_msg:
        extracted = await _extract_loan(last_msg, app_data)
        if extracted:
            app_data = {**app_data, **extracted}

    # Validate loan amount range
    loan_amt = app_data.get("loan_amount", 0)
    if loan_amt and (loan_amt < 1000 or loan_amt > 50000):
        return {
            "messages": [AIMessage(content=f"Our personal loans range from **$1,000 to $50,000**. "
                                          f"Could you choose an amount within that range?")],
            "current_stage": "loan_details",
            "applicant_data": app_data
        }

    missing = [f for f in ["loan_amount", "loan_purpose", "loan_term_months"] if not app_data.get(f)]
    if missing:
        return {
            "messages": [AIMessage(content=LOAN_QUESTIONS[missing[0]])],
            "current_stage": "loan_details",
            "applicant_data": app_data
        }

    # Calculate estimated payment
    term   = app_data["loan_term_months"]
    amount = app_data["loan_amount"]
    est_payment = _estimate_payment(amount, term)
    app_data["monthly_payment"] = est_payment

    purpose_label = app_data.get("loan_purpose", "").replace("_", " ").title()

    msg = (f"Great choices! Here's your loan summary:\n\n"
           f"| | |\n|---|---|\n"
           f"| **Amount** | ${amount:,.0f} |\n"
           f"| **Purpose** | {purpose_label} |\n"
           f"| **Term** | {term} months |\n"
           f"| **Est. Monthly Payment** | ~${est_payment:,.2f} |\n\n"
           f"*(Final rate determined after credit review)*\n\n"
           "To complete your application, I'll need a couple of documents:\n\n"
           "📎 Please upload:\n"
           "1. Your **2 most recent pay stubs**\n"
           "2. Your **last 2 years of tax returns** (W-2 or 1040)\n\n"
           "You can upload PDF or image files. Go ahead whenever you're ready!")

    return {
        "messages": [AIMessage(content=msg)],
        "current_stage": "document_upload",
        "applicant_data": app_data,
        "stages_complete": {**state.get("stages_complete", {}), "loan_details": True}
    }