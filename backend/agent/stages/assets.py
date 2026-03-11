# ============================================================
# backend/agent/stages/assets.py
# ============================================================
import json, logging, httpx
from langchain_core.messages import AIMessage, HumanMessage
from agent.state import LoanAgentState
from core.config import get_settings

logger = logging.getLogger(__name__)

ASSET_QUESTIONS = {
    "savings_amount":          "Do you have any **savings or checking account balances**? (total approximate amount, or say 'none')",
    "investment_amount":       "Do you have any **investments** — stocks, 401k, retirement accounts? (approximate total, or say 'none')",
    "property_value":          "Do you own any **property or real estate**? If yes, what is the approximate value? (or say 'none')",
    "monthly_rent":            "What is your **monthly rent or mortgage payment**?",
    "existing_loan_payments":  "Do you have any **existing loan payments** per month? (car loan, student loan, personal loan — total, or say 'none')",
    "credit_card_balance":     "What is your **total credit card balance** across all cards? (or say 'none')",
}

async def _extract_assets(msg: str, current: dict) -> dict:
    settings = get_settings()
    prompt = f"""Extract financial information from: "{msg}"
Return ONLY JSON with any found numeric fields:
savings_amount, investment_amount, property_value, monthly_rent,
existing_loan_payments, credit_card_balance (all floats, 0 if "none").
Convert "$5k" -> 5000.0, "$1,200/month" -> 1200.0.
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

ASSET_ORDER = ["savings_amount", "investment_amount", "property_value",
               "monthly_rent", "existing_loan_payments", "credit_card_balance"]

async def assets_node(state: LoanAgentState) -> dict:
    messages = state.get("messages", [])
    app_data = state.get("applicant_data", {})

    last_msg = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    if last_msg:
        extracted = await _extract_assets(last_msg, app_data)
        if extracted:
            app_data = {**app_data, **extracted}

    missing = [f for f in ASSET_ORDER if f not in app_data]
    if missing:
        return {
            "messages": [AIMessage(content=ASSET_QUESTIONS[missing[0]])],
            "current_stage": "assets_liabilities",
            "applicant_data": app_data
        }

    # Calculate total monthly obligations
    total_obligations = sum([
        app_data.get("monthly_rent", 0),
        app_data.get("existing_loan_payments", 0),
        app_data.get("credit_card_balance", 0) * 0.02,  # min payment estimate
    ])

    msg = (f"✅ Got it! Here's a quick summary of your financial picture:\n\n"
           f"• **Assets:** ${(app_data.get('savings_amount',0) + app_data.get('investment_amount',0)):,.0f}\n"
           f"• **Monthly obligations:** ~${total_obligations:,.0f}/month\n\n"
           "Now for the exciting part — let's talk about the loan itself!\n\n"
           "**How much would you like to borrow?**")

    return {
        "messages": [AIMessage(content=msg)],
        "current_stage": "loan_details",
        "applicant_data": app_data,
        "stages_complete": {**state.get("stages_complete", {}), "assets_liabilities": True}
    }

