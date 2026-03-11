import logging
import json
import httpx
from langchain_core.messages import AIMessage, HumanMessage
from agent.state import LoanAgentState
from agent.stages.base import call_llm
from core.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM = """You are Alex, a friendly loan officer. You are collecting identity information.
Extract information from user messages. Be conversational and warm.
Ask for one piece of information at a time. Never sound like a form."""

REQUIRED_FIELDS = ["first_name", "last_name", "email", "phone",
                   "date_of_birth", "ssn_last_four",
                   "street_address", "city", "state", "zip_code"]

FIELD_QUESTIONS = {
    "first_name":    "Could you tell me your **full legal name**?",
    "email":         "What's the best **email address** to reach you?",
    "phone":         "And your **phone number**?",
    "date_of_birth": "What is your **date of birth**? (MM/DD/YYYY)",
    "ssn_last_four": "For identity verification, I'll need the **last 4 digits of your Social Security Number**.",
    "street_address":"What is your **current home address**? (start with street address)",
    "city":          "Which **city** do you live in?",
    "state":         "What **state**?",
    "zip_code":      "And your **zip code**?",
}

async def _extract_fields(user_msg: str, current_data: dict) -> dict:
    """Ask LLM to extract identity fields from user message."""
    settings = get_settings()
    already = list(current_data.keys())
    prompt = f"""Extract identity information from this message: "{user_msg}"

Already collected: {already}
Return ONLY a JSON object with any of these fields found: first_name, last_name, email, phone, date_of_birth, ssn_last_four, street_address, city, state, zip_code
If a field contains both first and last name, split them.
If nothing found, return {{}}.
Return ONLY the JSON, no explanation. /no_think"""

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/generate",
            json={"model": settings.ollama_model, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.1, "num_predict": 4096}}
        )
        text = resp.json().get("response", "{}")

    try:
        start, end = text.find("{"), text.rfind("}") + 1
        return json.loads(text[start:end]) if start >= 0 else {}
    except Exception:
        return {}

async def _run_socure(data: dict, mock_hub_url: str) -> dict:
    """Tool call — Socure ID verification."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{mock_hub_url}/socure/verify-identity", json={
            "first_name":    data.get("first_name", ""),
            "last_name":     data.get("last_name", ""),
            "date_of_birth": data.get("date_of_birth", ""),
            "ssn_last_four": data.get("ssn_last_four", ""),
            "email":         data.get("email", ""),
            "phone":         data.get("phone", ""),
            "street_address":data.get("street_address", ""),
            "city":          data.get("city", ""),
            "state":         data.get("state", ""),
            "zip_code":      data.get("zip_code", ""),
        })
        return resp.json()

async def identity_node(state: LoanAgentState) -> dict:
    messages  = state.get("messages", [])
    app_data  = state.get("applicant_data", {})
    settings  = get_settings()

    # Extract from latest user message
    last_user_msg = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            last_user_msg = m.content
            break

    if last_user_msg:
        extracted = await _extract_fields(last_user_msg, app_data)
        if extracted:
            app_data = {**app_data, **extracted}

    # Find next missing field
    missing = [f for f in REQUIRED_FIELDS if not app_data.get(f)]

    if missing:
        next_field = missing[0]
        question = FIELD_QUESTIONS.get(next_field,
            f"Could you provide your {next_field.replace('_', ' ')}?")
        return {
            "messages":      [AIMessage(content=question)],
            "current_stage": "identity",
            "applicant_data": app_data,
            "last_tool_called": None
        }

    # All fields collected — run Socure
    try:
        logger.info(f"Running Socure ID verification for session {state['session_id']}")
        result = await _run_socure(app_data, settings.mock_hub_url)
        status = result.get("status", "FAIL")

        if status == "FAIL":
            msg = ("I'm sorry, but I wasn't able to verify your identity with the information provided. "
                   "This could be due to a mismatch in our records. "
                   "Would you like to speak with one of our specialists? Just say 'speak to agent'.")
            return {
                "messages": [AIMessage(content=msg)],
                "current_stage": "identity",
                "applicant_data": app_data,
                "identity_result": result,
                "last_tool_called": "socure_verify"
            }

        if status == "REVIEW":
            msg = ("Thank you! Your identity is under a brief review — this is a routine step and shouldn't take long. "
                   "Let's continue with your application while that completes.\n\n"
                   "Could you tell me about your **current employment status**? "
                   "(e.g. employed full-time, self-employed, retired)")
        else:
            msg = ("✅ Identity verified successfully!\n\n"
                   "Now let's talk about your employment. "
                   "What is your current **employment status**? "
                   "(e.g. employed full-time, self-employed, retired)")

        return {
            "messages": [AIMessage(content=msg)],
            "current_stage": "employment",
            "applicant_data": app_data,
            "identity_result": result,
            "stages_complete": {**state.get("stages_complete", {}), "identity": True},
            "last_tool_called": "socure_verify"
        }

    except Exception as e:
        logger.error(f"Socure error: {e}")
        return {
            "messages": [AIMessage(content="I'm having trouble verifying your identity right now. Let's continue and we'll sort this out. What is your employment status?")],
            "current_stage": "employment",
            "applicant_data": app_data,
            "stages_complete": {**state.get("stages_complete", {}), "identity": True}
        }
