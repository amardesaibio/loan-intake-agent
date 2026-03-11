# ============================================================
# backend/agent/stages/decision.py
# ============================================================
import logging, httpx
from langchain_core.messages import AIMessage
from agent.state import LoanAgentState
from agent.stages.base import call_llm
from core.config import get_settings
from db import repository as repo

logger = logging.getLogger(__name__)

# ── Decision Rules ────────────────────────────────────────────

def _apply_rules(credit: dict, app_data: dict) -> dict:
    score  = credit.get("credit_score", 0)
    dti    = app_data.get("debt_to_income_ratio", 99)
    amount = app_data.get("loan_amount", 0)
    annual = app_data.get("annual_income", 1)
    derogs = credit.get("derogatory_marks", 0)
    lti    = app_data.get("loan_to_income_ratio", 99)

    reasons = []

    # Hard stops
    if score < 580:
        reasons.append("CREDIT_SCORE_BELOW_MINIMUM")
        return {"outcome": "auto_decline", "reasons": reasons, "score": score, "rate": None}

    if dti > 50:
        reasons.append("DTI_EXCEEDS_MAXIMUM")
        return {"outcome": "auto_decline", "reasons": reasons, "score": score, "rate": None}

    if derogs > 2:
        reasons.append("EXCESSIVE_DEROGATORY_MARKS")
        return {"outcome": "auto_decline", "reasons": reasons, "score": score, "rate": None}

    # Auto approve tiers
    if score >= 720 and dti <= 35 and derogs == 0:
        return {"outcome": "auto_approve", "reasons": ["EXCELLENT_CREDIT_PROFILE"],
                "score": score, "rate": 7.99}

    if score >= 680 and dti <= 40:
        return {"outcome": "auto_approve", "reasons": ["GOOD_CREDIT_PROFILE"],
                "score": score, "rate": 11.99}

    if score >= 660 and dti <= 43:
        return {"outcome": "auto_approve", "reasons": ["ACCEPTABLE_CREDIT_PROFILE"],
                "score": score, "rate": 15.99}

    # Refer to underwriter
    if score >= 620:
        reasons.append("MANUAL_REVIEW_REQUIRED")
        if dti > 43: reasons.append("ELEVATED_DTI")
        if derogs > 0: reasons.append("DEROGATORY_MARKS_PRESENT")
        return {"outcome": "refer_underwriter", "reasons": reasons, "score": score, "rate": None}

    reasons.append("CREDIT_SCORE_INSUFFICIENT")
    return {"outcome": "auto_decline", "reasons": reasons, "score": score, "rate": None}

def _calc_payment(amount: float, term: int, rate: float) -> float:
    mr = rate / 100 / 12
    return round(amount * (mr * (1 + mr)**term) / ((1 + mr)**term - 1), 2)

async def decision_node(state: LoanAgentState) -> dict:
    app_data = state.get("applicant_data", {})
    credit   = state.get("credit_result", {})
    settings = get_settings()

    # Guard: already decided — don't re-run rules or re-send emails
    existing_outcome = state.get("decision_outcome")
    if existing_outcome in ("auto_decline", "refer_underwriter"):
        return {
            "messages": [AIMessage(content="Your application has already been reviewed. Is there anything else I can help you with?")],
            "current_stage": "decision",
        }

    if not credit:
        return {
            "messages": [AIMessage(content="Let me retrieve your credit results first...")],
            "current_stage": "credit_check"
        }

    rules = _apply_rules(credit, app_data)
    outcome  = rules["outcome"]
    reasons  = rules["reasons"]
    rate     = rules.get("rate")
    amount   = app_data.get("loan_amount", 0)
    term     = app_data.get("loan_term_months", 36)

    decision_details = {
        "outcome":  outcome,
        "reasons":  reasons,
        "credit_score": credit.get("credit_score"),
        "dti":      app_data.get("debt_to_income_ratio"),
        "rate":     rate,
    }

    if outcome == "auto_approve":
        payment = _calc_payment(amount, term, rate)
        app_data["interest_rate"]  = rate
        app_data["monthly_payment"] = payment
        decision_details["monthly_payment"] = payment

        logger.info(f"[Decision] outcome=auto_approve score={credit.get('credit_score')} dti={app_data.get('debt_to_income_ratio')} rate={rate}% payment=${payment}")

        # Persist decision
        application_id = state.get("application_id")
        if application_id:
            try:
                await repo.save_decision(
                    application_id=application_id,
                    outcome="auto_approve",
                    app_data=app_data,
                    credit=credit,
                    decision_details=decision_details,
                )
            except Exception as e:
                logger.warning(f"[DB] save_decision (approve) failed: {e}")

        # Send approval email
        email_payload = {
            "to_email":  app_data.get("email",""),
            "to_name":   f"{app_data.get('first_name','')} {app_data.get('last_name','')}",
            "template":  "approved",
            "variables": {
                "name":            f"{app_data.get('first_name','')}",
                "app_number":      state.get("application_number","N/A"),
                "loan_amount":     amount,
                "interest_rate":   rate,
                "term":            term,
                "monthly_payment": payment,
            }
        }
        logger.info(f"[Email] REQUEST → POST /email/send (approved): to={email_payload['to_email']} template={email_payload['template']}")
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                resp = await c.post(f"{settings.mock_hub_url}/email/send", json=email_payload)
                logger.info(f"[Email] RESPONSE ← {resp.status_code}: {resp.json()}")
        except Exception as e:
            logger.warning(f"Approval email failed: {e}")

        msg = (f"🎉 **Congratulations, {app_data.get('first_name','')}! You're approved!**\n\n"
               f"| | |\n|---|---|\n"
               f"| **Approved Amount** | ${amount:,.0f} |\n"
               f"| **Interest Rate** | {rate}% APR |\n"
               f"| **Term** | {term} months |\n"
               f"| **Monthly Payment** | ${payment:,.2f} |\n\n"
               "An approval email has been sent to you.\n\n"
               "**Next step:** Please review and sign your loan agreement. "
               "I'm generating your document now... 📄")

        return {
            "messages":        [AIMessage(content=msg)],
            "current_stage":   "decision",
            "applicant_data":  app_data,
            "decision_outcome": "auto_approve",
            "decision_details": decision_details,
            "stages_complete": {**state.get("stages_complete", {}), "decision": True},
            "last_tool_called": "decision_engine"
        }

    elif outcome == "auto_decline":
        reason_text = ", ".join(r.replace("_", " ").title() for r in reasons)

        logger.info(f"[Decision] outcome=auto_decline score={credit.get('credit_score')} reasons={reasons}")

        # Persist decision
        application_id = state.get("application_id")
        if application_id:
            try:
                await repo.save_decision(
                    application_id=application_id,
                    outcome="auto_decline",
                    app_data=app_data,
                    credit=credit,
                    decision_details=decision_details,
                )
            except Exception as e:
                logger.warning(f"[DB] save_decision (decline) failed: {e}")

        email_payload = {
            "to_email": app_data.get("email",""),
            "to_name":  f"{app_data.get('first_name','')} {app_data.get('last_name','')}",
            "template": "declined",
            "variables": {"name": app_data.get("first_name",""), "app_number": state.get("application_number","N/A"), "reasons": reason_text}
        }
        logger.info(f"[Email] REQUEST → POST /email/send (declined): to={email_payload['to_email']} reasons={reason_text}")
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                resp = await c.post(f"{settings.mock_hub_url}/email/send", json=email_payload)
                logger.info(f"[Email] RESPONSE ← {resp.status_code}: {resp.json()}")
        except Exception as e:
            logger.warning(f"Decline email failed: {e}")

        msg = (f"I'm sorry, {app_data.get('first_name','')}, but after reviewing your application "
               f"we're unable to approve it at this time.\n\n"
               f"**Reason(s):** {reason_text}\n\n"
               "You'll receive a formal adverse action notice by email within 24 hours.\n\n"
               "You're welcome to reapply in 90 days, or if you'd like to discuss your options "
               "with one of our specialists, just say **'speak to an agent'**.")

        return {
            "messages":        [AIMessage(content=msg)],
            "current_stage":   "decision",
            "decision_outcome": "auto_decline",
            "decision_details": decision_details,
            "stages_complete": {**state.get("stages_complete", {}), "decision": True},
        }

    else:  # refer_underwriter
        reason_text = ", ".join(r.replace("_", " ").title() for r in reasons)

        logger.info(f"[Decision] outcome=refer_underwriter score={credit.get('credit_score')} reasons={reasons}")

        # Persist decision
        application_id = state.get("application_id")
        if application_id:
            try:
                await repo.save_decision(
                    application_id=application_id,
                    outcome="refer_underwriter",
                    app_data=app_data,
                    credit=credit,
                    decision_details=decision_details,
                )
            except Exception as e:
                logger.warning(f"[DB] save_decision (refer) failed: {e}")

        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                applicant_email = {
                    "to_email": app_data.get("email",""),
                    "to_name":  f"{app_data.get('first_name','')} {app_data.get('last_name','')}",
                    "template": "referred_underwriter",
                    "variables": {"name": app_data.get("first_name",""), "app_number": state.get("application_number","N/A")}
                }
                logger.info(f"[Email] REQUEST → POST /email/send (refer applicant): to={applicant_email['to_email']}")
                resp = await c.post(f"{settings.mock_hub_url}/email/send", json=applicant_email)
                logger.info(f"[Email] RESPONSE ← {resp.status_code}: {resp.json()}")

                uw_email = {
                    "to_email": "underwriting@loanagent.local",
                    "to_name":  "Underwriting Team",
                    "template": "referred_underwriter",
                    "variables": {"name": f"{app_data.get('first_name','')} {app_data.get('last_name','')}", "app_number": state.get("application_number","N/A")}
                }
                logger.info(f"[Email] REQUEST → POST /email/send (notify UW team): to={uw_email['to_email']}")
                resp2 = await c.post(f"{settings.mock_hub_url}/email/send", json=uw_email)
                logger.info(f"[Email] RESPONSE ← {resp2.status_code}: {resp2.json()}")
        except Exception as e:
            logger.warning(f"UW referral email failed: {e}")

        msg = (f"Thank you for your patience, {app_data.get('first_name','')}.\n\n"
               "Your application has been referred to our **underwriting team** for a detailed review. "
               "This is a normal part of our process for applications that need additional consideration.\n\n"
               f"**What happens next:**\n"
               "• Our underwriters will review your application within **5–7 business days**\n"
               "• You'll receive an email with their decision\n"
               "• We may contact you if additional information is needed\n\n"
               f"**Reference:** {state.get('application_number','N/A')}\n\n"
               "A confirmation email has been sent to you. Is there anything else I can help you with?")

        return {
            "messages":        [AIMessage(content=msg)],
            "current_stage":   "decision",
            "decision_outcome": "refer_underwriter",
            "decision_details": decision_details,
            "stages_complete": {**state.get("stages_complete", {}), "decision": True},
        }
