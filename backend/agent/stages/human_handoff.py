
# ============================================================
# backend/agent/stages/human_handoff.py
# ============================================================
import logging, httpx
from langchain_core.messages import AIMessage
from agent.state import LoanAgentState
from core.config import get_settings

logger = logging.getLogger(__name__)

async def human_handoff_node(state: LoanAgentState) -> dict:
    app_data = state.get("applicant_data", {})
    settings = get_settings()
    name     = f"{app_data.get('first_name','')} {app_data.get('last_name','')}".strip() or "Applicant"
    reason   = state.get("handoff_reason", "Customer requested assistance")

    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            await c.post(f"{settings.mock_hub_url}/email/send", json={
                "to_email": app_data.get("email",""),
                "to_name":  name,
                "template": "human_handoff",
                "variables": {
                    "name":       app_data.get("first_name",""),
                    "app_number": state.get("application_number","N/A"),
                }
            })
    except Exception as e:
        logger.warning(f"Handoff email failed: {e}")

    msg = (f"Of course, {app_data.get('first_name','') or 'there'}! I'm connecting you with a loan specialist now.\n\n"
           "**What happens next:**\n"
           "• A specialist will contact you within **2 business hours**\n"
           "• They'll reach you at the phone number or email on your application\n"
           "• Your conversation history has been shared with them\n\n"
           f"**Your reference number:** `{state.get('session_id','')[:8].upper()}`\n\n"
           "A confirmation email has been sent to you.\n\n"
           "Is there anything else you'd like me to note for the specialist?")

    return {
        "messages":     [AIMessage(content=msg)],
        "current_stage": "human_handoff",
        "human_handoff": True,
    }