# ============================================================
# backend/db/models.py  — SQLAlchemy ORM models
# ============================================================
from sqlalchemy import (
    Column, String, Float, Integer, Boolean,
    DateTime, Text, ForeignKey, ARRAY
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from db.session import Base

# ── Applicant ────────────────────────────────────────────────
class Applicant(Base):
    __tablename__ = "applicants"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id          = Column(String(255), unique=True, nullable=False, index=True)
    first_name          = Column(String(100))
    last_name           = Column(String(100))
    email               = Column(String(255), index=True)
    phone               = Column(String(20))
    date_of_birth       = Column(String(20))
    ssn_last_four       = Column(String(4))
    street_address      = Column(String(255))
    city                = Column(String(100))
    state               = Column(String(50))
    zip_code            = Column(String(10))
    years_at_address    = Column(Float)
    employment_status   = Column(String(50))
    employer_name       = Column(String(255))
    job_title           = Column(String(255))
    years_employed      = Column(Float)
    annual_income       = Column(Float)
    monthly_income      = Column(Float)
    other_income        = Column(Float)
    other_income_source = Column(String(255))
    savings_amount      = Column(Float)
    investment_amount   = Column(Float)
    property_value      = Column(Float)
    monthly_rent        = Column(Float)
    existing_loan_payments = Column(Float)
    credit_card_balance = Column(Float)
    other_monthly_debts = Column(Float)
    consent_given       = Column(Boolean, default=False)
    consent_timestamp   = Column(DateTime(timezone=True))
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    applications = relationship("Application", back_populates="applicant")

# ── Application ──────────────────────────────────────────────
class Application(Base):
    __tablename__ = "applications"

    id                    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    applicant_id          = Column(UUID(as_uuid=True), ForeignKey("applicants.id"), nullable=False)
    application_number    = Column(String(20), unique=True)
    loan_amount           = Column(Float)
    loan_purpose          = Column(String(50))
    loan_term_months      = Column(Integer)
    interest_rate         = Column(Float)
    monthly_payment       = Column(Float)
    status                = Column(String(50), default="started")
    current_stage         = Column(String(50), default="welcome")
    credit_score          = Column(Integer)
    debt_to_income_ratio  = Column(Float)
    loan_to_income_ratio  = Column(Float)
    submitted_to_uw_at    = Column(DateTime(timezone=True))
    uw_reference_number   = Column(String(100))
    docusign_envelope_id  = Column(String(255))
    docusign_signed_at    = Column(DateTime(timezone=True))
    is_human_handoff      = Column(Boolean, default=False)
    handoff_reason        = Column(Text)
    created_at            = Column(DateTime(timezone=True), server_default=func.now())
    updated_at            = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    applicant             = relationship("Applicant", back_populates="applications")
    documents             = relationship("Document", back_populates="application")
    verification_results  = relationship("VerificationResult", back_populates="application")
    decisions             = relationship("Decision", back_populates="application")

# ── Verification Result ──────────────────────────────────────
class VerificationResult(Base):
    __tablename__ = "verification_results"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False)
    service_name   = Column(String(50), nullable=False)
    status         = Column(String(20), default="pending")
    raw_response   = Column(JSONB)
    summary        = Column(JSONB)
    called_at      = Column(DateTime(timezone=True), server_default=func.now())
    completed_at   = Column(DateTime(timezone=True))

    application    = relationship("Application", back_populates="verification_results")

# ── Decision ─────────────────────────────────────────────────
class Decision(Base):
    __tablename__ = "decisions"

    id                       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id           = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False)
    outcome                  = Column(String(30), nullable=False)
    approved_amount          = Column(Float)
    approved_rate            = Column(Float)
    approved_term            = Column(Integer)
    approved_monthly_payment = Column(Float)
    reason_codes             = Column(JSONB)
    reason_narrative         = Column(Text)
    rules_result             = Column(JSONB)
    llm_assessment           = Column(Text)
    final_score              = Column(Float)
    decided_at               = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("Application", back_populates="decisions")

# ── Document ─────────────────────────────────────────────────
class Document(Base):
    __tablename__ = "documents"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id    = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False)
    document_type     = Column(String(50), nullable=False)
    original_filename = Column(String(255))
    stored_filename   = Column(String(255))
    file_path         = Column(Text)
    mime_type         = Column(String(100))
    file_size_bytes   = Column(Integer)
    extracted_data    = Column(JSONB)
    extraction_status = Column(String(50), default="pending")
    extraction_notes  = Column(Text)
    validation_passed = Column(Boolean)
    validation_notes  = Column(Text)
    uploaded_at       = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("Application", back_populates="documents")

# ── Conversation History ─────────────────────────────────────
class ConversationMessage(Base):
    __tablename__ = "conversation_history"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=True)
    session_id     = Column(String(255), nullable=False, index=True)
    role           = Column(String(20), nullable=False)
    content        = Column(Text, nullable=False)
    stage          = Column(String(50))
    msg_metadata   = Column("metadata", JSONB)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

# ── Human Handoff ────────────────────────────────────────────
class HumanHandoff(Base):
    __tablename__ = "human_handoffs"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id      = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=True)
    session_id          = Column(String(255), nullable=False, index=True)
    reason              = Column(Text)
    transcript_summary  = Column(Text)
    status              = Column(String(50), default="pending")
    agent_name          = Column(String(255))
    resolved_at         = Column(DateTime(timezone=True))
    created_at          = Column(DateTime(timezone=True), server_default=func.now())

# ── MCP Tool Calls ───────────────────────────────────────────
class MCPToolCall(Base):
    __tablename__ = "mcp_tool_calls"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=True)
    server_name    = Column(String(100), nullable=False)
    tool_name      = Column(String(100), nullable=False)
    input_params   = Column(JSONB)
    response       = Column(JSONB)
    duration_ms    = Column(Integer)
    success        = Column(Boolean)
    error_message  = Column(Text)
    called_at      = Column(DateTime(timezone=True), server_default=func.now())