# ============================================================
# backend/agent/stages/review.py
# ============================================================
import logging
from langchain_core.messages import AIMessage, HumanMessage
from agent.state import LoanAgentState
from agent.stages.document_upload import _build_summary

logger = logging.getLogger(__name__)

CONFIRM_WORDS = ["confirm", "yes", "correct", "looks good", "submit", "proceed", "approved", "go ahead", "all good"]

async def review_node(state: LoanAgentState) -> dict:
    messages = state.get("messages", [])
    app_data = state.get("applicant_data", {})

    last_msg = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "").lower()

    if any(w in last_msg for w in CONFIRM_WORDS):
        msg = ("✅ Application confirmed!\n\n"
               "🔍 I'm now running a **soft credit check** — this won't affect your credit score.\n\n"
               "This usually takes just a few seconds...")
        return {
            "messages": [AIMessage(content=msg)],
            "current_stage": "review",
            "stages_complete": {**state.get("stages_complete", {}), "review": True}
        }

    # Check if user wants to correct something
    if last_msg and last_msg not in ["", "skip"]:
        correction_prompt = (
            f"The applicant wants to correct something: '{last_msg}'\n"
            "Acknowledge the correction warmly and show the updated summary."
        )
        # For now just re-show summary with a note
        msg = (f"Of course! Please tell me exactly what you'd like to update and I'll fix it right away.\n\n"
               + _build_summary(app_data))
        return {
            "messages": [AIMessage(content=msg)],
            "current_stage": "review",
            "applicant_data": app_data
        }

    # First time hitting review — show summary
    return {
        "messages": [AIMessage(content=_build_summary(app_data))],
        "current_stage": "review"
    }

