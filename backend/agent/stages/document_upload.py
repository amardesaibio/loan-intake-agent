
# ============================================================
# backend/agent/stages/document_upload.py
# ============================================================
import logging
from langchain_core.messages import AIMessage, HumanMessage
from agent.state import LoanAgentState

logger = logging.getLogger(__name__)

SKIP_WORDS = ["skip", "no doc", "don't have", "later", "proceed", "continue without"]

async def document_upload_node(state: LoanAgentState) -> dict:
    messages      = state.get("messages", [])
    docs_uploaded = state.get("documents_uploaded", [])
    app_data      = state.get("applicant_data", {})

    last_msg = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "").lower()

    # Check if user wants to skip (POC allowance)
    skip = any(w in last_msg for w in SKIP_WORDS)

    has_paystub  = any(d.get("type") == "paystub"    for d in docs_uploaded)
    has_tax      = any(d.get("type") == "tax_return"  for d in docs_uploaded)

    if skip or (has_paystub and has_tax):
        if skip:
            note = ("No problem — you can provide documents later if needed. "
                    "We'll proceed with the information you've given us.\n\n")
        else:
            note = "✅ Documents received and verified!\n\n"

        msg = (note +
               "Let me now **summarise your entire application** for your review before we submit.\n\n"
               + _build_summary(app_data))

        return {
            "messages": [AIMessage(content=msg)],
            "current_stage": "review",
            "stages_complete": {**state.get("stages_complete", {}), "document_upload": True}
        }

    # Guide on what's still needed
    needed = []
    if not has_paystub:  needed.append("📄 Pay stub (last 2 months)")
    if not has_tax:      needed.append("📄 Tax return (last 2 years, W-2 or 1040)")

    msg = ("Please upload the following documents using the 📎 button below:\n\n" +
           "\n".join(f"• {n}" for n in needed) +
           "\n\nOr type **'skip'** to proceed without documents "
           "(may affect approval decision).")

    return {
        "messages": [AIMessage(content=msg)],
        "current_stage": "document_upload"
    }

def _build_summary(d: dict) -> str:
    name    = f"{d.get('first_name','')} {d.get('last_name','')}".strip()
    income  = d.get('annual_income', 0)
    monthly = d.get('monthly_income', 0)
    obligations = (d.get('monthly_rent',0) +
                   d.get('existing_loan_payments',0) +
                   d.get('credit_card_balance',0) * 0.02)
    return (
        f"**📋 Application Summary**\n\n"
        f"**Personal**\n"
        f"• Name: {name}\n"
        f"• Email: {d.get('email','—')}\n"
        f"• Address: {d.get('street_address','—')}, {d.get('city','—')}, {d.get('state','—')}\n\n"
        f"**Employment**\n"
        f"• Employer: {d.get('employer_name','—')}\n"
        f"• Title: {d.get('job_title','—')}\n"
        f"• Duration: {d.get('years_employed','—')} year(s)\n\n"
        f"**Finances**\n"
        f"• Annual Income: ${income:,.0f}\n"
        f"• Monthly Income: ${monthly:,.0f}\n"
        f"• Monthly Obligations: ~${obligations:,.0f}\n\n"
        f"**Loan Request**\n"
        f"• Amount: ${d.get('loan_amount',0):,.0f}\n"
        f"• Purpose: {d.get('loan_purpose','—').replace('_',' ').title()}\n"
        f"• Term: {d.get('loan_term_months','—')} months\n"
        f"• Est. Payment: ~${d.get('monthly_payment',0):,.2f}/month\n\n"
        f"Does everything look correct? Type **'confirm'** to submit, "
        f"or tell me what needs to be changed."
    )
