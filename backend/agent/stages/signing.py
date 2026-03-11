# ============================================================
# backend/agent/stages/signing.py
# ============================================================
import logging, httpx
from langchain_core.messages import AIMessage, HumanMessage
from agent.state import LoanAgentState
from core.config import get_settings
from db import repository as repo

logger = logging.getLogger(__name__)

async def signing_node(state: LoanAgentState) -> dict:
    app_data = state.get("applicant_data", {})
    settings = get_settings()

    # Already signed
    if state.get("document_signed"):
        return {
            "messages": [AIMessage(content="✅ Document already signed. Moving to onboarding...")],
            "current_stage": "onboarding",
            "stages_complete": {**state.get("stages_complete", {}), "signing": True}
        }

    # Create DocuSign envelope if not yet done
    envelope_id  = state.get("envelope_id")
    signing_url  = state.get("signing_url")

    if not envelope_id:
        try:
            ds_payload = {
                "applicant_name":   f"{app_data.get('first_name','')} {app_data.get('last_name','')}",
                "applicant_email":  app_data.get("email",""),
                "application_number": state.get("application_number","N/A"),
                "loan_amount":      app_data.get("loan_amount",0),
                "loan_term_months": app_data.get("loan_term_months",36),
                "interest_rate":    app_data.get("interest_rate",14.99),
                "monthly_payment":  app_data.get("monthly_payment",0),
            }
            logger.info(f"[DocuSign] REQUEST → POST /docusign/create-envelope: {ds_payload}")
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.post(f"{settings.mock_hub_url}/docusign/create-envelope", json=ds_payload)
                env = r.json()
            envelope_id = env.get("envelope_id")
            signing_url = env.get("signing_url")
            logger.info(f"[DocuSign] RESPONSE ← envelope_id={envelope_id} signing_url={signing_url} status={env.get('status')}")
        except Exception as e:
            logger.error(f"DocuSign error: {e}")
            return {
                "messages": [AIMessage(content="I'm having trouble generating your agreement. Let me try again in a moment.")],
                "current_stage": "signing"
            }

    # Check if already signed (poll status)
    try:
        logger.info(f"[DocuSign] REQUEST → GET /docusign/envelope/{envelope_id}/status")
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{settings.mock_hub_url}/docusign/envelope/{envelope_id}/status")
            status = r.json().get("status","")
        logger.info(f"[DocuSign] RESPONSE ← envelope_id={envelope_id} status={status}")

        if status == "COMPLETED":
            application_id = state.get("application_id")
            if application_id:
                try:
                    await repo.update_application_signed(
                        application_id=application_id,
                        envelope_id=envelope_id,
                    )
                except Exception as e:
                    logger.warning(f"[DB] update_application_signed failed: {e}")
            try:
                async with httpx.AsyncClient(timeout=10.0) as c:
                    await c.post(f"{settings.mock_hub_url}/email/send", json={
                        "to_email":  app_data.get("email",""),
                        "to_name":   app_data.get("first_name",""),
                        "template":  "document_signed",
                        "variables": {
                            "name":       app_data.get("first_name",""),
                            "app_number": state.get("application_number","N/A")
                        }
                    })
            except Exception:
                pass

            return {
                "messages": [AIMessage(content="✅ **Loan agreement signed!** Your documents have been recorded.\n\nLet's get you set up! 🎉")],
                "current_stage": "onboarding",
                "document_signed": True,
                "stages_complete": {**state.get("stages_complete", {}), "signing": True},
                "last_tool_called": "docusign_sign"
            }
    except Exception as e:
        logger.warning(f"Status check failed: {e}")

    # Present signing link
    msg = (f"📄 Your **Loan Agreement** is ready to sign!\n\n"
           f"Please click the link below to review and sign your agreement:\n\n"
           f"**[Sign Your Loan Agreement]({signing_url})**\n\n"
           "Once you've signed, come back and let me know by typing **'signed'** or **'done'**.\n\n"
           "*(The link is valid for 3 days)*")

    # Check if user says they signed
    messages = state.get("messages", [])
    last_msg = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "").lower()
    if any(w in last_msg for w in ["signed", "done", "completed", "finished"]):
        # Simulate webhook completing
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                await c.post(f"{settings.mock_hub_url}/docusign/webhook/simulate",
                    json={"envelope_id": envelope_id, "outcome": "COMPLETED"})
        except Exception:
            pass
        application_id = state.get("application_id")
        if application_id and envelope_id:
            try:
                await repo.update_application_signed(
                    application_id=application_id,
                    envelope_id=envelope_id,
                )
            except Exception as e:
                logger.warning(f"[DB] update_application_signed (self-report) failed: {e}")
        return {
            "messages": [AIMessage(content="✅ **Agreement signed and received!** Welcome to First Digital Bank! 🎉\n\nLet me get your account set up...")],
            "current_stage": "onboarding",
            "document_signed": True,
            "envelope_id":    envelope_id,
            "stages_complete": {**state.get("stages_complete", {}), "signing": True},
        }

    return {
        "messages":   [AIMessage(content=msg)],
        "current_stage": "signing",
        "envelope_id":   envelope_id,
        "signing_url":   signing_url,
        "last_tool_called": "docusign_create"
    }
