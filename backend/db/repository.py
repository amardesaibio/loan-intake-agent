# ============================================================
# backend/db/repository.py  — async persistence helpers
# ============================================================
"""
All DB writes go through this module.
Every function is fire-and-forget safe: callers should wrap in
try/except so a DB failure never crashes the agent.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.session import get_session_factory
from db.models import (
    Applicant, Application, VerificationResult,
    Decision, Document,
)

logger = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc)


# ── Application number generator ─────────────────────────────

def generate_application_number() -> str:
    """FDB-YYYYMMDD-XXXX  e.g. FDB-20240315-A3F9"""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:4].upper()
    return f"FDB-{today}-{suffix}"


# ── Applicant ─────────────────────────────────────────────────

async def upsert_applicant(session_id: str, app_data: dict) -> str:
    """
    Insert or update the Applicant row for this session.
    Returns the applicant UUID as a string.
    """
    factory = get_session_factory()
    async with factory() as db:
        # Check if applicant already exists for this session
        result = await db.execute(
            select(Applicant).where(Applicant.session_id == session_id)
        )
        applicant = result.scalar_one_or_none()

        fields = {
            "first_name":           app_data.get("first_name"),
            "last_name":            app_data.get("last_name"),
            "email":                app_data.get("email"),
            "phone":                app_data.get("phone"),
            "date_of_birth":        app_data.get("date_of_birth"),
            "ssn_last_four":        app_data.get("ssn_last_four"),
            "street_address":       app_data.get("street_address"),
            "city":                 app_data.get("city"),
            "state":                app_data.get("state"),
            "zip_code":             app_data.get("zip_code"),
            "years_at_address":     app_data.get("years_at_address"),
            "employment_status":    app_data.get("employment_status"),
            "employer_name":        app_data.get("employer_name"),
            "job_title":            app_data.get("job_title"),
            "years_employed":       app_data.get("years_employed"),
            "annual_income":        app_data.get("annual_income"),
            "monthly_income":       app_data.get("monthly_income"),
            "other_income":         app_data.get("other_income"),
            "other_income_source":  app_data.get("other_income_source"),
            "savings_amount":       app_data.get("savings_amount"),
            "investment_amount":    app_data.get("investment_amount"),
            "property_value":       app_data.get("property_value"),
            "monthly_rent":         app_data.get("monthly_rent"),
            "existing_loan_payments": app_data.get("existing_loan_payments"),
            "credit_card_balance":  app_data.get("credit_card_balance"),
            "other_monthly_debts":  app_data.get("other_monthly_debts"),
            "consent_given":        True,
            "consent_timestamp":    _now(),
            "updated_at":           _now(),
        }

        if applicant:
            for k, v in fields.items():
                if v is not None:
                    setattr(applicant, k, v)
        else:
            applicant = Applicant(session_id=session_id, **{k: v for k, v in fields.items() if v is not None})
            db.add(applicant)

        await db.commit()
        await db.refresh(applicant)
        applicant_id = str(applicant.id)
        logger.info(f"[DB] Applicant upserted: id={applicant_id} session={session_id}")
        return applicant_id


# ── Application ───────────────────────────────────────────────

async def create_or_update_application(
    applicant_id: str,
    app_data: dict,
    application_number: str = None,
    status: str = "started",
    current_stage: str = "gathering",
) -> tuple[str, str]:
    """
    Create or update the Application row.
    Returns (application_id, application_number).
    """
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(Application).where(Application.applicant_id == uuid.UUID(applicant_id))
        )
        application = result.scalar_one_or_none()

        if not application_number:
            application_number = generate_application_number()

        fields = {
            "loan_amount":       app_data.get("loan_amount"),
            "loan_purpose":      app_data.get("loan_purpose"),
            "loan_term_months":  app_data.get("loan_term_months"),
            "interest_rate":     app_data.get("interest_rate"),
            "monthly_payment":   app_data.get("monthly_payment"),
            "status":            status,
            "current_stage":     current_stage,
            "debt_to_income_ratio": app_data.get("debt_to_income_ratio"),
            "loan_to_income_ratio": app_data.get("loan_to_income_ratio"),
            "updated_at":        _now(),
        }

        if application:
            for k, v in fields.items():
                if v is not None:
                    setattr(application, k, v)
        else:
            application = Application(
                applicant_id=uuid.UUID(applicant_id),
                application_number=application_number,
                **{k: v for k, v in fields.items() if v is not None},
            )
            db.add(application)

        await db.commit()
        await db.refresh(application)
        app_id = str(application.id)
        app_num = application.application_number
        logger.info(f"[DB] Application saved: id={app_id} number={app_num} status={status}")
        return app_id, app_num


# ── Verification Results ──────────────────────────────────────

async def save_verification_result(
    application_id: str,
    service_name: str,
    status: str,
    raw_response: dict,
    summary: dict = None,
):
    """Insert a VerificationResult row."""
    factory = get_session_factory()
    async with factory() as db:
        row = VerificationResult(
            application_id=uuid.UUID(application_id),
            service_name=service_name,
            status=status,
            raw_response=raw_response,
            summary=summary or {},
            completed_at=_now(),
        )
        db.add(row)
        await db.commit()
        logger.info(f"[DB] VerificationResult saved: service={service_name} status={status} app_id={application_id}")


# ── Decision ──────────────────────────────────────────────────

async def save_decision(
    application_id: str,
    outcome: str,
    app_data: dict,
    credit: dict,
    decision_details: dict,
):
    """Insert a Decision row and update Application status."""
    factory = get_session_factory()
    async with factory() as db:
        # Insert decision
        decision = Decision(
            application_id=uuid.UUID(application_id),
            outcome=outcome,
            approved_amount=app_data.get("loan_amount") if outcome == "auto_approve" else None,
            approved_rate=decision_details.get("rate"),
            approved_term=app_data.get("loan_term_months") if outcome == "auto_approve" else None,
            approved_monthly_payment=app_data.get("monthly_payment") if outcome == "auto_approve" else None,
            reason_codes=decision_details.get("reasons", []),
            reason_narrative=", ".join(decision_details.get("reasons", [])),
            rules_result=decision_details,
            final_score=float(credit.get("credit_score", 0)),
        )
        db.add(decision)

        # Update application status
        status_map = {
            "auto_approve":      "approved",
            "auto_decline":      "declined",
            "refer_underwriter": "referred",
        }
        result = await db.execute(
            select(Application).where(Application.id == uuid.UUID(application_id))
        )
        application = result.scalar_one_or_none()
        if application:
            application.status = status_map.get(outcome, outcome)
            application.credit_score = credit.get("credit_score")
            application.debt_to_income_ratio = app_data.get("debt_to_income_ratio")
            application.interest_rate = decision_details.get("rate")
            application.monthly_payment = app_data.get("monthly_payment")
            application.updated_at = _now()

        await db.commit()
        logger.info(f"[DB] Decision saved: outcome={outcome} app_id={application_id}")


# ── Document ──────────────────────────────────────────────────

async def save_document(
    application_id: str,
    document_type: str,
    original_filename: str,
    stored_filename: str,
    file_path: str,
    mime_type: str,
    file_size_bytes: int,
):
    """Insert a Document row."""
    factory = get_session_factory()
    async with factory() as db:
        doc = Document(
            application_id=uuid.UUID(application_id),
            document_type=document_type,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=file_path,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            extraction_status="pending",
        )
        db.add(doc)
        await db.commit()
        logger.info(f"[DB] Document saved: type={document_type} app_id={application_id}")


# ── Signing ───────────────────────────────────────────────────

async def update_application_signed(
    application_id: str,
    envelope_id: str,
):
    """Mark application as signed in DB."""
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(Application).where(Application.id == uuid.UUID(application_id))
        )
        application = result.scalar_one_or_none()
        if application:
            application.docusign_envelope_id = envelope_id
            application.docusign_signed_at = _now()
            application.status = "signed"
            application.updated_at = _now()
            await db.commit()
            logger.info(f"[DB] Application signed: app_id={application_id} envelope={envelope_id}")
