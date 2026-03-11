-- ============================================================
-- Loan Intake Agent — Database Schema
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── ENUM Types ───────────────────────────────────────────────

CREATE TYPE application_status AS ENUM (
  'started',
  'in_progress',
  'submitted',
  'credit_check',
  'decision_pending',
  'approved',
  'declined',
  'referred_to_underwriter',
  'under_review',
  'signed',
  'onboarded',
  'abandoned',
  'human_handoff'
);

CREATE TYPE application_stage AS ENUM (
  'welcome',
  'identity',
  'employment',
  'income',
  'assets_liabilities',
  'loan_details',
  'document_upload',
  'review',
  'credit_check',
  'decision',
  'signing',
  'onboarding',
  'complete'
);

CREATE TYPE decision_outcome AS ENUM (
  'auto_approve',
  'auto_decline',
  'refer_underwriter'
);

CREATE TYPE verification_status AS ENUM (
  'pending',
  'passed',
  'failed',
  'review'
);

CREATE TYPE employment_status AS ENUM (
  'employed_full_time',
  'employed_part_time',
  'self_employed',
  'unemployed',
  'retired',
  'student'
);

CREATE TYPE loan_purpose AS ENUM (
  'debt_consolidation',
  'home_improvement',
  'medical',
  'vehicle',
  'education',
  'vacation',
  'wedding',
  'business',
  'other'
);

CREATE TYPE document_type AS ENUM (
  'paystub',
  'tax_return',
  'bank_statement',
  'id_document',
  'other'
);

-- ── APPLICANTS ───────────────────────────────────────────────

CREATE TABLE applicants (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id          VARCHAR(255) UNIQUE NOT NULL,

  -- Personal Info
  first_name          VARCHAR(100),
  last_name           VARCHAR(100),
  email               VARCHAR(255),
  phone               VARCHAR(20),
  date_of_birth       DATE,
  ssn_last_four       VARCHAR(4),
  ssn_encrypted       TEXT,  -- encrypted full SSN if collected

  -- Address
  street_address      VARCHAR(255),
  city                VARCHAR(100),
  state               VARCHAR(50),
  zip_code            VARCHAR(10),
  years_at_address    NUMERIC(4,1),

  -- Employment
  employment_status   employment_status,
  employer_name       VARCHAR(255),
  job_title           VARCHAR(255),
  years_employed      NUMERIC(4,1),
  employer_phone      VARCHAR(20),

  -- Income
  annual_income       NUMERIC(12,2),
  monthly_income      NUMERIC(12,2),
  other_income        NUMERIC(12,2),
  other_income_source VARCHAR(255),

  -- Assets
  savings_amount      NUMERIC(12,2),
  investment_amount   NUMERIC(12,2),
  property_value      NUMERIC(12,2),

  -- Liabilities
  monthly_rent        NUMERIC(10,2),
  existing_loan_payments NUMERIC(10,2),
  credit_card_balance NUMERIC(12,2),
  other_monthly_debts NUMERIC(10,2),

  -- Consent
  consent_given       BOOLEAN DEFAULT FALSE,
  consent_timestamp   TIMESTAMPTZ,

  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ── APPLICATIONS ─────────────────────────────────────────────

CREATE TABLE applications (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  applicant_id          UUID NOT NULL REFERENCES applicants(id),
  application_number    VARCHAR(20) UNIQUE NOT NULL,

  -- Loan Details
  loan_amount           NUMERIC(12,2),
  loan_purpose          loan_purpose,
  loan_term_months      INTEGER,  -- 12, 24, 36, 48, 60
  interest_rate         NUMERIC(5,2),
  monthly_payment       NUMERIC(10,2),

  -- Status
  status                application_status DEFAULT 'started',
  current_stage         application_stage DEFAULT 'welcome',

  -- Scores & Metrics
  credit_score          INTEGER,
  debt_to_income_ratio  NUMERIC(5,2),
  loan_to_income_ratio  NUMERIC(5,2),

  -- Underwriting
  submitted_to_uw_at    TIMESTAMPTZ,
  uw_reference_number   VARCHAR(100),
  uw_decision           VARCHAR(100),
  uw_decision_at        TIMESTAMPTZ,

  -- DocuSign
  docusign_envelope_id  VARCHAR(255),
  docusign_signed_at    TIMESTAMPTZ,

  -- Flags
  is_human_handoff      BOOLEAN DEFAULT FALSE,
  handoff_reason        TEXT,

  created_at            TIMESTAMPTZ DEFAULT NOW(),
  updated_at            TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-generate application number
CREATE SEQUENCE app_number_seq START 100001;
CREATE OR REPLACE FUNCTION generate_app_number()
RETURNS TRIGGER AS $$
BEGIN
  NEW.application_number := 'LN-' || LPAD(nextval('app_number_seq')::TEXT, 7, '0');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_app_number
BEFORE INSERT ON applications
FOR EACH ROW EXECUTE FUNCTION generate_app_number();

-- ── VERIFICATION RESULTS ─────────────────────────────────────

CREATE TABLE verification_results (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  application_id    UUID NOT NULL REFERENCES applications(id),
  service_name      VARCHAR(50) NOT NULL, -- socure, equifax, plaid, argyle
  status            verification_status DEFAULT 'pending',
  raw_response      JSONB,
  summary           JSONB,  -- extracted key fields
  called_at         TIMESTAMPTZ DEFAULT NOW(),
  completed_at      TIMESTAMPTZ
);

-- ── DECISIONS ────────────────────────────────────────────────

CREATE TABLE decisions (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  application_id      UUID NOT NULL REFERENCES applications(id),
  outcome             decision_outcome NOT NULL,

  -- Approval details
  approved_amount     NUMERIC(12,2),
  approved_rate       NUMERIC(5,2),
  approved_term       INTEGER,
  approved_monthly_payment NUMERIC(10,2),

  -- Decline / refer details
  reason_codes        TEXT[],
  reason_narrative    TEXT,  -- LLM generated explanation

  -- Rule engine output
  rules_result        JSONB,
  llm_assessment      TEXT,
  final_score         NUMERIC(5,2),

  decided_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ── DOCUMENTS ────────────────────────────────────────────────

CREATE TABLE documents (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  application_id      UUID NOT NULL REFERENCES applications(id),
  document_type       document_type NOT NULL,
  original_filename   VARCHAR(255),
  stored_filename     VARCHAR(255),
  file_path           TEXT,
  mime_type           VARCHAR(100),
  file_size_bytes     INTEGER,

  -- Extraction
  extracted_data      JSONB,
  extraction_status   VARCHAR(50) DEFAULT 'pending', -- pending, done, failed
  extraction_notes    TEXT,

  -- Validation
  validation_passed   BOOLEAN,
  validation_notes    TEXT,

  uploaded_at         TIMESTAMPTZ DEFAULT NOW()
);

-- ── CONVERSATION HISTORY ─────────────────────────────────────

CREATE TABLE conversation_history (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  application_id  UUID REFERENCES applications(id),
  session_id      VARCHAR(255) NOT NULL,
  role            VARCHAR(20) NOT NULL,  -- 'user', 'assistant', 'system', 'tool'
  content         TEXT NOT NULL,
  stage           application_stage,
  metadata        JSONB,  -- tool calls, stage transitions, etc.
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── HUMAN HANDOFFS ───────────────────────────────────────────

CREATE TABLE human_handoffs (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  application_id    UUID REFERENCES applications(id),
  session_id        VARCHAR(255) NOT NULL,
  reason            TEXT,
  transcript_summary TEXT,
  status            VARCHAR(50) DEFAULT 'pending', -- pending, assigned, resolved
  agent_name        VARCHAR(255),
  resolved_at       TIMESTAMPTZ,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- ── MCP TOOL CALLS LOG ───────────────────────────────────────

CREATE TABLE mcp_tool_calls (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  application_id  UUID REFERENCES applications(id),
  server_name     VARCHAR(100) NOT NULL,  -- plaid, argyle, docusign, underwriting
  tool_name       VARCHAR(100) NOT NULL,
  input_params    JSONB,
  response        JSONB,
  duration_ms     INTEGER,
  success         BOOLEAN,
  error_message   TEXT,
  called_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── INDEXES ──────────────────────────────────────────────────

CREATE INDEX idx_applicants_session ON applicants(session_id);
CREATE INDEX idx_applicants_email ON applicants(email);
CREATE INDEX idx_applications_applicant ON applications(applicant_id);
CREATE INDEX idx_applications_status ON applications(status);
CREATE INDEX idx_applications_number ON applications(application_number);
CREATE INDEX idx_verification_application ON verification_results(application_id);
CREATE INDEX idx_documents_application ON documents(application_id);
CREATE INDEX idx_conversation_session ON conversation_history(session_id);
CREATE INDEX idx_conversation_application ON conversation_history(application_id);
CREATE INDEX idx_handoffs_session ON human_handoffs(session_id);
CREATE INDEX idx_mcp_calls_application ON mcp_tool_calls(application_id);

-- ── UPDATED_AT TRIGGER ───────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER applicants_updated_at BEFORE UPDATE ON applicants
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER applications_updated_at BEFORE UPDATE ON applications
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
