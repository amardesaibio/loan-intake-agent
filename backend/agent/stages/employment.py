
# ============================================================
# backend/agent/stages/employment.py
# ============================================================
import json, logging, httpx
from langchain_core.messages import AIMessage, HumanMessage
from agent.state import LoanAgentState
from agent.stages.base import call_llm
from core.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM = """You are Alex, a friendly loan officer collecting employment information.
Be conversational, warm, and concise. Ask one question at a time."""

REQUIRED = ["employment_status", "employer_name", "job_title", "years_employed"]

QUESTIONS = {
    "employment_status": "What is your current **employment status**? (e.g. employed full-time, self-employed, part-time, retired, unemployed)",
    "employer_name":     "Who is your **employer** / company name?",
    "job_title":         "What is your **job title or role**?",
    "years_employed":    "How long have you been with your current employer? (e.g. 3 years, 18 months)",
}

STATUS_MAP = {
    "full": "employed_full_time", "employed": "employed_full_time",
    "part": "employed_part_time", "self": "self_employed",
    "freelance": "self_employed", "contractor": "self_employed",
    "retired": "retired", "unemployed": "unemployed",
    "student": "student"
}

async def _extract(msg: str, current: dict) -> dict:
    settings = get_settings()
    prompt = f"""Extract employment information from: "{msg}"
Already collected: {list(current.keys())}
Return ONLY JSON with any found fields: employment_status, employer_name, job_title, years_employed (as float).
For employment_status use one of: employed_full_time, employed_part_time, self_employed, unemployed, retired, student.
For years_employed convert to float (e.g. "3 years" -> 3.0, "18 months" -> 1.5).
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

async def employment_node(state: LoanAgentState) -> dict:
    messages = state.get("messages", [])
    app_data = state.get("applicant_data", {})
    settings = get_settings()

    last_msg = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    if last_msg:
        extracted = await _extract(last_msg, app_data)
        if extracted:
            app_data = {**app_data, **extracted}

    # Self-employed / unemployed skip employer fields
    status = app_data.get("employment_status", "")
    required = REQUIRED.copy()
    if status in ("unemployed", "retired", "student"):
        required = ["employment_status"]

    missing = [f for f in required if not app_data.get(f)]

    if missing:
        return {
            "messages": [AIMessage(content=QUESTIONS.get(missing[0], f"Please provide your {missing[0].replace('_',' ')}"))],
            "current_stage": "employment",
            "applicant_data": app_data
        }

    # Trigger Argyle (MCP) employment verification
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(f"{settings.mock_hub_url}/argyle/employment-record", json={
                "applicant_name":       f"{app_data.get('first_name','')} {app_data.get('last_name','')}",
                "employer_name":        app_data.get("employer_name", ""),
                "job_title":            app_data.get("job_title", ""),
                "stated_annual_salary": app_data.get("annual_income", 50000),
                "stated_years_employed":app_data.get("years_employed", 1.0),
            })
            emp_result = r.json()
        logger.info(f"Argyle verified: {emp_result.get('employer_verified')}")
    except Exception as e:
        logger.warning(f"Argyle call failed: {e}")
        emp_result = {}

    msg = (f"Great, thank you! I can see you've been with **{app_data.get('employer_name','your employer')}** "
           f"for about {app_data.get('years_employed','')} year(s). ✅\n\n"
           "Now let's look at your income. What is your **annual gross income** (before taxes)?")

    return {
        "messages": [AIMessage(content=msg)],
        "current_stage": "income",
        "applicant_data": app_data,
        "employment_result": emp_result,
        "stages_complete": {**state.get("stages_complete", {}), "employment": True},
        "last_tool_called": "argyle_verify"
    }