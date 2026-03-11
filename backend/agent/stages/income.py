# ============================================================
# backend/agent/stages/income.py
# ============================================================
import json, logging, httpx
from langchain_core.messages import AIMessage, HumanMessage
from agent.state import LoanAgentState
from core.config import get_settings

logger = logging.getLogger(__name__)

INCOME_REQUIRED = ["annual_income"]

INCOME_QUESTIONS = {
    "annual_income":      "What is your **annual gross income** (before taxes)? Please give me a dollar amount.",
    "other_income":       "Do you have any **other sources of income**? (rental, freelance, investments, etc.) If yes, how much per year? If no, just say none.",
}

async def _extract_income(msg: str, current: dict) -> dict:
    settings = get_settings()
    prompt = f"""Extract income information from: "{msg}"
Return ONLY JSON with any found: annual_income (float), other_income (float, 0 if none), other_income_source (string).
Convert amounts like "$75k" -> 75000.0, "$5,500/month" -> 66000.0 (annualised).
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

async def income_node(state: LoanAgentState) -> dict:
    messages = state.get("messages", [])
    app_data = state.get("applicant_data", {})
    settings = get_settings()

    last_msg = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    if last_msg:
        extracted = await _extract_income(last_msg, app_data)
        if extracted:
            app_data = {**app_data, **extracted}

    # Compute monthly from annual
    if app_data.get("annual_income") and not app_data.get("monthly_income"):
        app_data["monthly_income"] = round(app_data["annual_income"] / 12, 2)

    # Check if we asked about other income yet
    if not app_data.get("annual_income"):
        return {
            "messages": [AIMessage(content=INCOME_QUESTIONS["annual_income"])],
            "current_stage": "income",
            "applicant_data": app_data
        }

    if "other_income" not in app_data:
        return {
            "messages": [AIMessage(content=INCOME_QUESTIONS["other_income"])],
            "current_stage": "income",
            "applicant_data": app_data
        }

    # Run Plaid income verification (MCP)
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(f"{settings.mock_hub_url}/plaid/income-report", json={
                "applicant_name":       f"{app_data.get('first_name','')} {app_data.get('last_name','')}",
                "stated_annual_income": app_data.get("annual_income", 0),
                "employer_name":        app_data.get("employer_name", ""),
            })
            income_result = r.json()
        verified = income_result.get("verified", False)
        match_pct = income_result.get("income_match_pct", 100)
        logger.info(f"Plaid income verified={verified}, match={match_pct}%")
    except Exception as e:
        logger.warning(f"Plaid call failed: {e}")
        income_result = {}

    annual = app_data.get("annual_income", 0)
    monthly = app_data.get("monthly_income", 0)
    msg = (f"✅ Income noted — **${annual:,.0f}/year** (${monthly:,.0f}/month).\n\n"
           "Now let's get a picture of your assets and existing debts.\n\n"
           "Starting with assets — do you have any **savings or checking account balances**? "
           "If yes, roughly how much total?")

    return {
        "messages": [AIMessage(content=msg)],
        "current_stage": "assets_liabilities",
        "applicant_data": app_data,
        "income_result": income_result,
        "stages_complete": {**state.get("stages_complete", {}), "income": True},
        "last_tool_called": "plaid_income"
    }