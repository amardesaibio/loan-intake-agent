# ============================================================
# backend/agent/stages/credit_check.py
# ============================================================
import logging, httpx
from langchain_core.messages import AIMessage
from agent.state import LoanAgentState
from core.config import get_settings
from db import repository as repo

logger = logging.getLogger(__name__)

async def credit_check_node(state: LoanAgentState) -> dict:
    app_data = state.get("applicant_data", {})
    settings = get_settings()

    # Already ran — mark complete and let routing advance automatically
    if state.get("credit_result"):
        return {
            "messages": [AIMessage(content="Credit check already complete. Reviewing now...")],
            "current_stage": "credit_check",
            "stages_complete": {**state.get("stages_complete", {}), "credit_check": True}
        }

    try:
        payload = {
            "first_name":           app_data.get("first_name", ""),
            "last_name":            app_data.get("last_name", ""),
            "date_of_birth":        app_data.get("date_of_birth", ""),
            "ssn_last_four":        app_data.get("ssn_last_four", ""),
            "street_address":       app_data.get("street_address", ""),
            "zip_code":             app_data.get("zip_code", ""),
            "loan_amount_requested":app_data.get("loan_amount", 0),
        }
        logger.info(f"[Equifax] REQUEST → POST /equifax/credit-report: {payload}")
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(f"{settings.mock_hub_url}/equifax/credit-report", json=payload)
            credit = r.json()

        score = credit.get("credit_score", 0)
        grade = credit.get("risk_grade", "?")
        logger.info(
            f"[Equifax] RESPONSE ← score={score} grade={grade} "
            f"dti_monthly={credit.get('total_monthly_payments')} "
            f"utilization={credit.get('credit_utilization_pct')}% "
            f"derogatory_marks={credit.get('derogatory_marks')}"
        )

        # Calculate DTI
        monthly_income  = app_data.get("monthly_income", 1)
        monthly_debts   = (app_data.get("monthly_rent", 0) +
                          app_data.get("existing_loan_payments", 0) +
                          credit.get("total_monthly_payments", 0))
        new_payment     = app_data.get("monthly_payment", 0)
        dti             = round((monthly_debts + new_payment) / monthly_income * 100, 1) if monthly_income else 99

        # LTI
        lti = round(app_data.get("loan_amount", 0) / app_data.get("annual_income", 1), 2)

        msg = (f"✅ Credit check complete!\n\n"
               f"| | |\n|---|---|\n"
               f"| **Credit Score** | {score} ({grade}) |\n"
               f"| **Debt-to-Income** | {dti}% |\n"
               f"| **Credit Utilisation** | {credit.get('credit_utilization_pct',0)}% |\n\n"
               "Evaluating your application now... 🔄")

        updated_app_data = {**app_data, "debt_to_income_ratio": dti, "loan_to_income_ratio": lti}

        # Persist Equifax result
        application_id = state.get("application_id")
        if application_id:
            try:
                await repo.save_verification_result(
                    application_id=application_id,
                    service_name="equifax",
                    status="pass" if score >= 580 else "fail",
                    raw_response=credit,
                    summary={"credit_score": score, "grade": grade, "dti": dti, "lti": lti},
                )
                # Update application with credit metrics
                await repo.create_or_update_application(
                    applicant_id=state.get("applicant_id", ""),
                    app_data=updated_app_data,
                    application_number=state.get("application_number"),
                    status="credit_checked",
                    current_stage="credit_check",
                )
            except Exception as e:
                logger.warning(f"[DB] credit_check persistence failed: {e}")

        return {
            "messages":    [AIMessage(content=msg)],
            "current_stage": "credit_check",
            "credit_result": credit,
            "applicant_data": updated_app_data,
            "stages_complete": {**state.get("stages_complete", {}), "credit_check": True},
            "last_tool_called": "equifax_credit"
        }

    except Exception as e:
        logger.error(f"Credit check error: {e}")
        return {
            "messages": [AIMessage(content="I had trouble running the credit check. Let me try again in a moment...")],
            "current_stage": "credit_check"
        }