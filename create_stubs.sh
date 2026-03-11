#!/bin/bash
# Run from loan-intake-agent/ root
# Creates all missing __init__.py files and stage stubs

set -e
echo "📁 Creating package __init__.py files..."

touch backend/__init__.py
touch backend/api/__init__.py
touch backend/agent/__init__.py
touch backend/db/__init__.py
touch backend/core/__init__.py
touch backend/integrations/__init__.py
touch backend/services/__init__.py
touch backend/middleware/__init__.py

mkdir -p backend/agent/stages
touch backend/agent/stages/__init__.py

echo "✅ __init__.py files created"

# ── base.py — shared LLM caller + stub helper ────────────────
cat > backend/agent/stages/base.py << 'PYEOF'
"""
Shared utilities for all stage nodes.
Every stage node receives LoanAgentState and returns a partial state update.
"""
import logging
import httpx
from langchain_core.messages import AIMessage
from agent.state import LoanAgentState
from core.config import get_settings

logger = logging.getLogger(__name__)

async def call_llm(prompt: str, system: str = None) -> str:
    """Direct Ollama call — returns response text."""
    settings = get_settings()
    payload = {
        "model":  settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 512}
    }
    if system:
        payload["system"] = system

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/generate",
            json=payload
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

async def stub_node(state: LoanAgentState) -> dict:
    """Placeholder for unimplemented stages — returns a holding message."""
    stage = state.get("current_stage", "unknown")
    return {
        "messages": [AIMessage(content=f"[Stage '{stage}' is being built. Stay tuned!]")]
    }
PYEOF
echo "✅ base.py created"

# ── welcome.py ───────────────────────────────────────────────
cat > backend/agent/stages/welcome.py << 'PYEOF'
import logging
from langchain_core.messages import AIMessage, HumanMessage
from agent.state import LoanAgentState
from agent.stages.base import call_llm

logger = logging.getLogger(__name__)

SYSTEM = """You are Alex, a friendly and professional loan officer at First Digital Bank.
Your job is to guide applicants through a personal loan application in a warm, conversational way.
Be concise — no more than 3-4 sentences per response. Never ask more than one question at a time."""

WELCOME_MSG = """Hi there! 👋 I'm Alex, your personal loan advisor at First Digital Bank.

I'll guide you through our simple loan application — it takes about 10 minutes and I'll be with you every step of the way.

Before we begin, I need your consent to collect and process your personal and financial information to evaluate your loan application. This includes a soft credit check which **won't affect your credit score**.

Do you agree to proceed? (yes / no)"""

async def welcome_node(state: LoanAgentState) -> dict:
    messages = state.get("messages", [])
    applicant_data = state.get("applicant_data", {})

    # First visit — send welcome message
    if not messages or (len(messages) == 1 and isinstance(messages[0], HumanMessage)):
        if len(messages) == 0:
            return {
                "messages": [AIMessage(content=WELCOME_MSG)],
                "current_stage": "welcome"
            }

    # Check if user gave consent
    last_user_msg = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            last_user_msg = m.content.lower().strip()
            break

    consent_words = ["yes", "yeah", "yep", "sure", "ok", "okay", "agree", "i agree", "proceed", "continue"]
    decline_words = ["no", "nope", "decline", "don't", "do not", "cancel"]

    if any(w in last_user_msg for w in consent_words):
        return {
            "messages": [AIMessage(content="Great, thank you! 🎉 Let's get started.\n\nFirst, could you tell me your **full legal name**?")],
            "current_stage": "identity",
            "applicant_data": {**applicant_data, "consent_given": True},
            "stages_complete": {**state.get("stages_complete", {}), "welcome": True}
        }

    if any(w in last_user_msg for w in decline_words):
        return {
            "messages": [AIMessage(content="No problem at all! If you change your mind, feel free to come back anytime. Is there anything else I can help you with?")],
            "current_stage": "welcome"
        }

    # Unclear — re-prompt
    response = await call_llm(
        prompt=f"The applicant said: '{last_user_msg}'. They need to either consent or decline to proceed with a loan application. Politely ask them to confirm yes or no.",
        system=SYSTEM
    )
    return {
        "messages": [AIMessage(content=response)],
        "current_stage": "welcome"
    }
PYEOF
echo "✅ welcome.py created"

# ── identity.py ───────────────────────────────────────────────
cat > backend/agent/stages/identity.py << 'PYEOF'
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
Return ONLY the JSON, no explanation."""

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/generate",
            json={"model": settings.ollama_model, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.1, "num_predict": 256}}
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
PYEOF
echo "✅ identity.py created"

# ── Remaining stages as clean stubs ──────────────────────────
for stage in employment income assets loan_details document_upload review credit_check decision signing onboarding human_handoff; do

LABEL=$(echo $stage | sed 's/_/ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1))tolower(substr($i,2));}1')

cat > backend/agent/stages/${stage}.py << PYEOF
"""Stage: ${LABEL} — full implementation coming next."""
import logging
from langchain_core.messages import AIMessage
from agent.state import LoanAgentState

logger = logging.getLogger(__name__)

async def ${stage}_node(state: LoanAgentState) -> dict:
    return {
        "messages": [AIMessage(content="[${LABEL} stage — building now. Please stand by.]")],
        "current_stage": "${stage}"
    }
PYEOF

done

echo "✅ All stage stubs created"

# ── __init__.py for missing packages ─────────────────────────
mkdir -p backend/core backend/db backend/api backend/integrations backend/services backend/middleware
for d in backend/core backend/db backend/api backend/integrations backend/services backend/middleware; do
  touch $d/__init__.py
done

echo ""
echo "🎉 All stubs created. Rebuild backend:"
echo "   docker compose build backend && docker compose up -d backend"
echo "   docker compose logs backend -f --tail=30"
