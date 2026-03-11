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
            "messages": [AIMessage(content="Great, thank you! 🎉 Let's get started.\n\nFeel free to share your information in whatever order is convenient for you — I'll guide you through anything that's still needed.\n\nFirst, could you tell me your **full legal name**?")],
            "current_stage": "gathering",
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
