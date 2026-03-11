# ============================================================
# backend/agent/stages/onboarding.py
# ============================================================
import logging, httpx
from langchain_core.messages import AIMessage
from agent.state import LoanAgentState
from core.config import get_settings

logger = logging.getLogger(__name__)

async def onboarding_node(state: LoanAgentState) -> dict:
    app_data = state.get("applicant_data", {})
    settings = get_settings()
    name     = app_data.get("first_name","")
    amount   = app_data.get("loan_amount",0)
    payment  = app_data.get("monthly_payment",0)

    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            await c.post(f"{settings.mock_hub_url}/email/send", json={
                "to_email": app_data.get("email",""),
                "to_name":  name,
                "template": "application_received",
                "variables": {
                    "name":       name,
                    "app_number": state.get("application_number","N/A"),
                    "loan_amount": amount,
                }
            })
    except Exception as e:
        logger.warning(f"Onboarding email failed: {e}")

    msg = (f"🎊 **Welcome to First Digital Bank, {name}!**\n\n"
           "Your loan has been fully processed. Here's what happens next:\n\n"
           f"**💰 Funds Disbursement**\n"
           "Your loan funds will be deposited into your nominated account within **1–2 business days**.\n\n"
           f"**📅 First Payment**\n"
           f"Your first payment of **${payment:,.2f}** will be due 30 days from today.\n\n"
           "**📱 Account Access**\n"
           "• Download our **First Digital Bank** app\n"
           "• Use your email to register: " + app_data.get("email","") + "\n"
           "• Set up **AutoPay** to never miss a payment\n\n"
           f"**📞 Need help?**\n"
           "• Call us: 1-800-LOAN-HELP\n"
           "• Email: support@firstdigitalbank.com\n\n"
           f"Reference: `{state.get('application_number','N/A')}`\n\n"
           "**Congratulations and thank you for choosing First Digital Bank!** 🏦\n\n"
           "Is there anything else I can help you with today?")

    return {
        "messages": [AIMessage(content=msg)],
        "current_stage": "complete",
        "stages_complete": {**state.get("stages_complete", {}), "onboarding": True, "complete": True}
    }
