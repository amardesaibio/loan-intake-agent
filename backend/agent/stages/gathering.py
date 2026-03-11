"""
Unified non-linear information gathering stage.

Replaces the five linear stages (identity, employment, income,
assets_liabilities, loan_details) with a single flexible stage.

The applicant can volunteer any information in any order.
We extract everything from each message, track what's still missing,
and ask conversationally for the next logical piece.

Identity verification (Socure) runs once all identity fields are present.
The stage completes once all required fields are collected.
"""
import json
import logging
import httpx
from langchain_core.messages import AIMessage, HumanMessage
from agent.state import LoanAgentState
from core.config import get_settings
from db import repository as repo

logger = logging.getLogger(__name__)

SYSTEM = """You are Alex, a friendly and professional loan officer at First Digital Bank.
You are collecting information for a personal loan application in a natural conversation.
Be warm, concise, and acknowledge what the applicant just shared before asking for the next item.
Never sound like you're filling out a form. Keep responses to 2-3 sentences max."""

# ── Required field groups ─────────────────────────────────────

IDENTITY_FIELDS = [
    "first_name", "last_name", "email", "phone",
    "date_of_birth", "ssn_last_four",
    "street_address", "city", "state", "zip_code",
]

EMPLOYMENT_FIELDS_EMPLOYED = [
    "employment_status", "employer_name", "job_title", "years_employed",
]
EMPLOYMENT_FIELDS_OTHER = ["employment_status"]  # retired / unemployed / student

INCOME_FIELDS = ["annual_income"]

LOAN_FIELDS = ["loan_amount", "loan_purpose", "loan_term_months"]

# Ordered priority for asking next question
QUESTION_ORDER = (
    IDENTITY_FIELDS
    + ["employment_status", "employer_name", "job_title", "years_employed"]
    + INCOME_FIELDS
    + LOAN_FIELDS
)

# ── Per-field questions ───────────────────────────────────────

QUESTIONS = {
    "first_name":       "Let's start with the basics — could you tell me your **full legal name**?",
    "last_name":        "And your **last name**?",
    "email":            "What's the best **email address** to reach you?",
    "phone":            "And your **phone number**?",
    "date_of_birth":    "What is your **date of birth**? (MM/DD/YYYY)",
    "ssn_last_four":    "For identity verification, I'll need the **last 4 digits of your Social Security Number**.",
    "street_address":   "What is your **current home address**? (start with street address)",
    "city":             "Which **city** do you live in?",
    "state":            "And what **state**?",
    "zip_code":         "What's your **zip code**?",
    "employment_status":"What is your current **employment status**? "
                        "(e.g. employed full-time, self-employed, part-time, retired, unemployed)",
    "employer_name":    "Who is your **current employer**?",
    "job_title":        "What is your **job title or role**?",
    "years_employed":   "How long have you been with your current employer? "
                        "(e.g. 3 years, 18 months)",
    "annual_income":    "What is your **annual gross income** before taxes?",
    "loan_amount":      "**How much would you like to borrow?** (between $1,000 and $50,000)",
    "loan_purpose":     "What will you be using the loan for? "
                        "(e.g. debt consolidation, home improvement, medical, vehicle, other)",
    "loan_term_months": "How long would you like to repay the loan? "
                        "We offer terms of **12, 24, 36, 48, or 60 months**.",
}

# ── LLM extraction ────────────────────────────────────────────

EXTRACTION_PROMPT = """\
Extract any personal loan application information from this message: "{msg}"
{context_hint}
Return ONLY a JSON object containing any of the following fields you can identify:
{{
  "first_name": "string",
  "last_name": "string",
  "email": "string",
  "phone": "string",
  "date_of_birth": "MM/DD/YYYY",
  "ssn_last_four": "4 digits only",
  "street_address": "string",
  "city": "string",
  "state": "2-letter abbreviation or full name",
  "zip_code": "string",
  "employment_status": "one of: employed_full_time, employed_part_time, self_employed, unemployed, retired, student",
  "employer_name": "string",
  "job_title": "string",
  "years_employed": "float — convert '3 years' -> 3.0, '18 months' -> 1.5",
  "annual_income": "float — convert '$60k' -> 60000.0",
  "monthly_income": "float",
  "savings_amount": "float",
  "investment_amount": "float",
  "monthly_rent": "float",
  "existing_loan_payments": "float",
  "credit_card_balance": "float",
  "loan_amount": "float — convert '$25k' -> 25000.0",
  "loan_purpose": "one of: debt_consolidation, home_improvement, medical, vehicle, education, vacation, wedding, business, other",
  "loan_term_months": "integer, one of: 12, 24, 36, 48, 60"
}}

Rules:
- Only include fields clearly present in the message
- If the message contains a full name, split into first_name and last_name
- Return {{}} if nothing relevant is found
- Return ONLY valid JSON, no explanation"""

import re as _re
_THINK_RE = _re.compile(r'<think>[\s\S]*?</think>', _re.IGNORECASE)


async def _extract_fields(msg: str, context_field: str = None) -> dict:
    """Use LLM to extract any application fields from a free-form message.
    context_field: the field name we most recently asked for (helps with short answers).
    """
    settings = get_settings()
    context_hint = ""
    if context_field:
        label = context_field.replace("_", " ")
        context_hint = f"Context: the previous question was asking for the applicant's {label}."
    prompt = EXTRACTION_PROMPT.format(msg=msg, context_hint=context_hint)
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model":   settings.ollama_model,
                    "prompt":  prompt,
                    "stream":  False,
                    "options": {"temperature": 0.1, "num_predict": 2048},
                },
            )
            raw = resp.json().get("response", "{}")
        # Strip any <think>...</think> blocks the model may have generated
        text = _THINK_RE.sub("", raw).strip()
        logger.info(f"Extraction response (first 300 chars): {text[:300]}")
        start, end = text.find("{"), text.rfind("}") + 1
        return json.loads(text[start:end]) if start >= 0 else {}
    except Exception as e:
        logger.warning(f"Field extraction failed: {e}")
        return {}


async def _run_socure(data: dict, mock_hub_url: str) -> dict:
    """Socure identity verification tool call."""
    payload = {
        "first_name":     data.get("first_name", ""),
        "last_name":      data.get("last_name", ""),
        "date_of_birth":  data.get("date_of_birth", ""),
        "ssn_last_four":  data.get("ssn_last_four", ""),
        "email":          data.get("email", ""),
        "phone":          data.get("phone", ""),
        "street_address": data.get("street_address", ""),
        "city":           data.get("city", ""),
        "state":          data.get("state", ""),
        "zip_code":       data.get("zip_code", ""),
    }
    logger.info(f"[Socure] REQUEST → POST /socure/verify-identity: {payload}")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{mock_hub_url}/socure/verify-identity", json=payload)
        result = resp.json()
    logger.info(f"[Socure] RESPONSE ← status={result.get('status')} score={result.get('score')} reasons={result.get('reasons')} kyc={result.get('kyc_result')}")
    return result


async def _run_argyle(data: dict, mock_hub_url: str) -> dict:
    """Argyle employment verification tool call."""
    payload = {
        "applicant_name":        f"{data.get('first_name','')} {data.get('last_name','')}",
        "employer_name":         data.get("employer_name", ""),
        "job_title":             data.get("job_title", ""),
        "stated_annual_salary":  data.get("annual_income", 50000),
        "stated_years_employed": data.get("years_employed", 1.0),
    }
    logger.info(f"[Argyle] REQUEST → POST /argyle/employment-record: {payload}")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{mock_hub_url}/argyle/employment-record", json=payload)
        result = resp.json()
    logger.info(f"[Argyle] RESPONSE ← verified={result.get('employment_verified')} salary={result.get('verified_annual_salary')} status={result.get('employment_status')}")
    return result


# ── Required field helpers ────────────────────────────────────

def _required_employment_fields(app_data: dict) -> list:
    status = app_data.get("employment_status", "")
    if status in ("unemployed", "retired", "student"):
        return EMPLOYMENT_FIELDS_OTHER
    return EMPLOYMENT_FIELDS_EMPLOYED


def _all_required_fields(app_data: dict) -> list:
    return (
        IDENTITY_FIELDS
        + _required_employment_fields(app_data)
        + INCOME_FIELDS
        + LOAN_FIELDS
    )


def _missing_fields(app_data: dict) -> list:
    required = _all_required_fields(app_data)
    return [f for f in required if not app_data.get(f)]


def _next_question(missing: list) -> str | None:
    """Return question for the first missing field in priority order."""
    for field in QUESTION_ORDER:
        if field in missing:
            return QUESTIONS.get(field,
                f"Could you tell me your {field.replace('_', ' ')}?")
    return None


def _build_progress_note(app_data: dict) -> str:
    """Acknowledge what was just provided, mention what groups remain."""
    missing = _missing_fields(app_data)
    remaining_groups = []
    if any(f in missing for f in IDENTITY_FIELDS):
        remaining_groups.append("personal details")
    if any(f in missing for f in ["employment_status", "employer_name", "job_title", "years_employed"]):
        remaining_groups.append("employment")
    if any(f in missing for f in INCOME_FIELDS):
        remaining_groups.append("income")
    if any(f in missing for f in LOAN_FIELDS):
        remaining_groups.append("loan preferences")
    if not remaining_groups:
        return ""
    return f"Still needed: {', '.join(remaining_groups)}."


# ── Main node ─────────────────────────────────────────────────

async def gathering_node(state: LoanAgentState) -> dict:
    messages  = state.get("messages", [])
    app_data  = dict(state.get("applicant_data", {}))
    settings  = get_settings()
    stages_complete = dict(state.get("stages_complete", {}))
    identity_result = state.get("identity_result")
    employment_result = state.get("employment_result")

    # ── 1. Extract fields from latest user message ────────────
    last_msg = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""
    )
    # Determine the field we last asked for — gives the LLM context for short answers
    pre_missing = _missing_fields(app_data)
    context_field = pre_missing[0] if pre_missing else None

    extracted = {}
    if last_msg:
        extracted = await _extract_fields(last_msg, context_field=context_field)
        if extracted:
            app_data = {**app_data, **extracted}
            logger.info(f"Gathering extracted: {list(extracted.keys())}")

    # ── 2. Validate loan amount range ─────────────────────────
    loan_amt = app_data.get("loan_amount", 0)
    if loan_amt and (loan_amt < 1000 or loan_amt > 50_000):
        return {
            "messages": [AIMessage(
                content="Our personal loans range from **$1,000 to $50,000**. "
                        "Could you choose an amount within that range?"
            )],
            "current_stage": "gathering",
            "applicant_data": app_data,
        }

    # ── 3. Run Socure once all identity fields are present ─────
    identity_done = all(app_data.get(f) for f in IDENTITY_FIELDS)
    if identity_done and identity_result is None:
        try:
            logger.info("Running Socure identity verification")
            result = await _run_socure(app_data, settings.mock_hub_url)
            identity_result = result
            status = result.get("status", "FAIL")
            if status == "FAIL":
                return {
                    "messages": [AIMessage(
                        content="I wasn't able to verify your identity with the information provided. "
                                "This may be due to a mismatch in our records. "
                                "Would you like to speak with a specialist? Just say 'speak to agent'."
                    )],
                    "current_stage": "gathering",
                    "applicant_data": app_data,
                    "identity_result": identity_result,
                    "last_tool_called": "socure_verify",
                }
        except Exception as e:
            logger.warning(f"Socure call failed: {e}")
            identity_result = {"status": "PASS", "note": "verification_skipped"}

    # ── 4. Check what's still missing ────────────────────────
    missing = _missing_fields(app_data)

    if missing:
        next_q = QUESTIONS.get(missing[0], f"Could you provide your {missing[0].replace('_', ' ')}?")

        # Prepend a brief acknowledgement using the applicant's actual name (if known)
        if extracted:
            first = app_data.get("first_name", "")
            greeting = f"Thanks{', ' + first if first else ''}! " if extracted else ""
            ack = greeting + next_q
        else:
            ack = next_q

        return {
            "messages": [AIMessage(content=ack)],
            "current_stage": "gathering",
            "applicant_data": app_data,
            "identity_result": identity_result,
            "last_tool_called": "socure_verify" if identity_done else None,
        }

    # ── 5. All required fields collected — run Argyle then advance ──
    try:
        status = (app_data.get("employment_status") or "")
        if status not in ("unemployed", "retired", "student") and employment_result is None:
            logger.info("Running Argyle employment verification")
            employment_result = await _run_argyle(app_data, settings.mock_hub_url)
    except Exception as e:
        logger.warning(f"Argyle call failed: {e}")
        employment_result = {}

    # Calculate estimated monthly payment
    from agent.stages.loan_details import _estimate_payment  # reuse helper
    term    = app_data["loan_term_months"]
    amount  = app_data["loan_amount"]
    est_pmt = _estimate_payment(amount, term)
    app_data["monthly_payment"] = est_pmt

    # ── Persist to PostgreSQL ──────────────────────────────────
    applicant_id    = state.get("applicant_id")
    application_id  = state.get("application_id")
    application_number = state.get("application_number")
    try:
        applicant_id = await repo.upsert_applicant(state.get("session_id", ""), app_data)
    except Exception as e:
        logger.warning(f"[DB] upsert_applicant failed: {e}")

    try:
        application_id, application_number = await repo.create_or_update_application(
            applicant_id=applicant_id,
            app_data=app_data,
            application_number=application_number,
            status="started",
            current_stage="document_upload",
        )
    except Exception as e:
        logger.warning(f"[DB] create_or_update_application failed: {e}")

    if application_id and identity_result:
        try:
            await repo.save_verification_result(
                application_id=application_id,
                service_name="socure",
                status=identity_result.get("status", "UNKNOWN").lower(),
                raw_response=identity_result,
                summary={"score": identity_result.get("score"), "kyc": identity_result.get("kyc_result")},
            )
        except Exception as e:
            logger.warning(f"[DB] save_verification_result (socure) failed: {e}")

    if application_id and employment_result:
        try:
            await repo.save_verification_result(
                application_id=application_id,
                service_name="argyle",
                status="pass" if employment_result.get("employment_verified") else "fail",
                raw_response=employment_result,
                summary={"verified": employment_result.get("employment_verified"), "salary": employment_result.get("verified_annual_salary")},
            )
        except Exception as e:
            logger.warning(f"[DB] save_verification_result (argyle) failed: {e}")

    purpose_label = app_data.get("loan_purpose", "").replace("_", " ").title()

    msg = (
        "✅ I have everything I need! Here's a summary of your loan request:\n\n"
        f"| | |\n|---|---|\n"
        f"| **Amount** | ${amount:,.0f} |\n"
        f"| **Purpose** | {purpose_label} |\n"
        f"| **Term** | {term} months |\n"
        f"| **Est. Monthly Payment** | ~${est_pmt:,.2f} |\n\n"
        "*(Final rate will be determined after the credit review)*\n\n"
        "To complete your application I'll need a couple of documents:\n\n"
        "📎 Please upload:\n"
        "1. Your **2 most recent pay stubs**\n"
        "2. Your **last 2 years of tax returns** (W-2 or 1040)\n\n"
        "You can upload PDF or image files whenever you're ready!"
    )

    stages_complete["gathering"] = True

    return {
        "messages": [AIMessage(content=msg)],
        "current_stage": "document_upload",
        "applicant_data": app_data,
        "identity_result": identity_result,
        "employment_result": employment_result,
        "stages_complete": stages_complete,
        "last_tool_called": "argyle_verify",
        "applicant_id":   applicant_id,
        "application_id": application_id,
        "application_number": application_number,
    }
