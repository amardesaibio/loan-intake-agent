"""
LangGraph Agent State — the single source of truth
that flows through every node in the graph.
"""
from typing import Optional, Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

# ── Stage Definitions ────────────────────────────────────────

STAGES = [
    "welcome",
    "gathering",
    "document_upload",
    "review",
    "credit_check",
    "decision",
    "signing",
    "onboarding",
    "complete"
]

STAGE_LABELS = {
    "welcome":         "Welcome & Consent",
    "gathering":       "Information Gathering",
    "document_upload": "Document Upload",
    "review":          "Review & Confirm",
    "credit_check":    "Credit Check",
    "decision":        "Decision",
    "signing":         "Sign Agreement",
    "onboarding":      "Onboarding",
    "complete":        "Complete"
}

# ── Application Data collected across stages ─────────────────

class ApplicantData(TypedDict, total=False):
    # Identity
    first_name:         str
    last_name:          str
    email:              str
    phone:              str
    date_of_birth:      str
    ssn_last_four:      str
    street_address:     str
    city:               str
    state:              str
    zip_code:           str
    years_at_address:   float
    consent_given:      bool

    # Employment
    employment_status:  str
    employer_name:      str
    job_title:          str
    years_employed:     float
    employer_phone:     str

    # Income
    annual_income:      float
    monthly_income:     float
    other_income:       float
    other_income_source: str

    # Assets
    savings_amount:     float
    investment_amount:  float
    property_value:     float

    # Liabilities
    monthly_rent:       float
    existing_loan_payments: float
    credit_card_balance: float
    other_monthly_debts: float

    # Loan
    loan_amount:        float
    loan_purpose:       str
    loan_term_months:   int

# ── Main Graph State ─────────────────────────────────────────

class LoanAgentState(TypedDict):
    # LangGraph managed message list (append-only)
    messages: Annotated[list, add_messages]

    # Session & application identifiers
    session_id:         str
    applicant_id:       Optional[str]
    application_id:     Optional[str]
    application_number: Optional[str]

    # Current stage in the flow
    current_stage:      str
    previous_stage:     Optional[str]

    # All collected applicant data
    applicant_data:     ApplicantData

    # Stage completion flags
    stages_complete:    dict  # { stage_name: bool }

    # Verification results (from tool calls)
    identity_result:    Optional[dict]   # Socure
    credit_result:      Optional[dict]   # Equifax
    income_result:      Optional[dict]   # Plaid (MCP)
    employment_result:  Optional[dict]   # Argyle (MCP)

    # Decision
    decision_outcome:   Optional[str]    # auto_approve / auto_decline / refer_underwriter
    decision_details:   Optional[dict]

    # DocuSign (MCP)
    envelope_id:        Optional[str]
    signing_url:        Optional[str]
    document_signed:    bool

    # Human handoff
    human_handoff:      bool
    handoff_reason:     Optional[str]

    # Document upload tracking
    documents_uploaded: list   # list of { type, filename, extracted_data }

    # Internal flags
    needs_clarification: bool
    error_message:      Optional[str]
    last_tool_called:   Optional[str]

# ── Initial state factory ────────────────────────────────────

def initial_state(session_id: str) -> LoanAgentState:
    return LoanAgentState(
        messages            = [],
        session_id          = session_id,
        applicant_id        = None,
        application_id      = None,
        application_number  = None,
        current_stage       = "welcome",
        previous_stage      = None,
        applicant_data      = {},
        stages_complete     = {s: False for s in STAGES},
        identity_result     = None,
        credit_result       = None,
        income_result       = None,
        employment_result   = None,
        decision_outcome    = None,
        decision_details    = None,
        envelope_id         = None,
        signing_url         = None,
        document_signed     = False,
        human_handoff       = False,
        handoff_reason      = None,
        documents_uploaded  = [],
        needs_clarification = False,
        error_message       = None,
        last_tool_called    = None,
    )