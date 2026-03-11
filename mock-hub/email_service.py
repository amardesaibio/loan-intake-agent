# ============================================================
# mock-hub/email_service.py — Email Notifications via MailHog
# ============================================================
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi import APIRouter as EmailRouter
from pydantic import BaseModel as EmailBase
import os, uuid
from datetime import datetime, timezone
from typing import Optional

email_router = EmailRouter()

MAILHOG_HOST = os.getenv("MAILHOG_HOST", "mailhog")
MAILHOG_PORT = int(os.getenv("MAILHOG_PORT", "1025"))
EMAIL_FROM   = os.getenv("EMAIL_FROM", "noreply@loanagent.local")

EMAIL_TEMPLATES = {
    "application_received": {
        "subject": "We received your loan application — {app_number}",
        "body": """
<h2>Thank you, {name}!</h2>
<p>We have received your personal loan application <strong>{app_number}</strong>.</p>
<p><strong>Requested Amount:</strong> ${loan_amount:,.2f}</p>
<p>Our team is reviewing your application. You will hear from us within <strong>1–3 business days</strong>.</p>
<p>Reference Number: <code>{app_number}</code></p>
"""
    },
    "approved": {
        "subject": "🎉 Congratulations! Your loan is approved — {app_number}",
        "body": """
<h2>Great news, {name}!</h2>
<p>Your personal loan application has been <strong style="color:green">APPROVED</strong>.</p>
<table>
  <tr><td><strong>Approved Amount:</strong></td><td>${loan_amount:,.2f}</td></tr>
  <tr><td><strong>Interest Rate:</strong></td><td>{interest_rate}% APR</td></tr>
  <tr><td><strong>Term:</strong></td><td>{term} months</td></tr>
  <tr><td><strong>Monthly Payment:</strong></td><td>${monthly_payment:,.2f}</td></tr>
</table>
<p>Please check your application portal to review and sign your loan agreement.</p>
"""
    },
    "declined": {
        "subject": "Update on your loan application — {app_number}",
        "body": """
<h2>Dear {name},</h2>
<p>Thank you for applying for a personal loan with us.</p>
<p>After careful review, we are unable to approve your application at this time.</p>
<p><strong>Reason(s):</strong> {reasons}</p>
<p>You have the right to request a free copy of your credit report within 60 days.</p>
<p>You are welcome to reapply in 90 days.</p>
"""
    },
    "referred_underwriter": {
        "subject": "Your application is under review — {app_number}",
        "body": """
<h2>Dear {name},</h2>
<p>Your loan application <strong>{app_number}</strong> has been referred to our underwriting team for a detailed review.</p>
<p>This process typically takes <strong>5–7 business days</strong>.</p>
<p>We will contact you if we need any additional information.</p>
"""
    },
    "document_signed": {
        "subject": "Loan agreement signed — {app_number}",
        "body": """
<h2>Dear {name},</h2>
<p>We have received your signed loan agreement for application <strong>{app_number}</strong>.</p>
<p>Your funds will be disbursed within <strong>1–2 business days</strong>.</p>
"""
    },
    "human_handoff": {
        "subject": "A team member will contact you — {app_number}",
        "body": """
<h2>Dear {name},</h2>
<p>We understand you requested to speak with one of our loan specialists.</p>
<p>A team member will contact you within <strong>2 business hours</strong> at the phone number or email on your application.</p>
<p>Your reference number is: <code>{app_number}</code></p>
"""
    }
}

class EmailRequest(EmailBase):
    to_email: str
    to_name: str
    template: str
    variables: dict = {}

class EmailResponse(EmailBase):
    message_id: str
    status: str
    template: str
    to: str
    timestamp: str

@email_router.post("/send", response_model=EmailResponse)
async def send_email(req: EmailRequest):
    template = EMAIL_TEMPLATES.get(req.template)
    if not template:
        return EmailResponse(
            message_id = "",
            status     = "ERROR",
            template   = req.template,
            to         = req.to_email,
            timestamp  = datetime.now(timezone.utc).isoformat()
        )

    subject = template["subject"].format(**req.variables)
    body    = template["body"].format(**req.variables)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = req.to_email
    msg["X-Message-ID"] = f"<{uuid.uuid4().hex}@loanagent.local>"
    msg.attach(MIMEText(body, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname = MAILHOG_HOST,
            port     = MAILHOG_PORT,
            start_tls = False
        )
        status = "SENT"
    except Exception as e:
        status = f"FAILED: {str(e)}"

    return EmailResponse(
        message_id = msg["X-Message-ID"],
        status     = status,
        template   = req.template,
        to         = req.to_email,
        timestamp  = datetime.now(timezone.utc).isoformat()
    )

@email_router.get("/templates")
async def list_templates():
    return {"templates": list(EMAIL_TEMPLATES.keys())}

# Make router importable
router = email_router