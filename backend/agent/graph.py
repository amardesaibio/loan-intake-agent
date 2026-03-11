"""
LangGraph state machine — wires all stages together.
Each node is a stage handler. Edges define valid transitions.
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agent.state import LoanAgentState
from agent.stages.welcome import welcome_node
from agent.stages.gathering import gathering_node
from agent.stages.document_upload import document_upload_node
from agent.stages.review import review_node
from agent.stages.credit_check import credit_check_node
from agent.stages.decision import decision_node
from agent.stages.signing import signing_node
from agent.stages.onboarding import onboarding_node
from agent.stages.human_handoff import human_handoff_node
from agent.stages.base import stub_node  # fallback for unimplemented stages

import logging
logger = logging.getLogger(__name__)
def entry_router(state: LoanAgentState) -> str:
    """Route to the correct stage node based on current_stage in state."""
    if state.get("human_handoff"):
        return "handoff_agent"
    stage = state.get("current_stage", "welcome")
    # Valid node names
    valid_nodes = [
        "welcome", "gathering", "document_upload",
        "review", "credit_check", "decision", "signing",
        "onboarding", "handoff_agent"
    ]
    return stage if stage in valid_nodes else "welcome"
# ── Router — decides next node after each stage ──────────────

def route_after_stage(state: LoanAgentState) -> str:
    """Central router — only advances when a stage is marked complete."""

    # Human handoff always takes priority
    if state.get("human_handoff"):
        return "handoff_agent"

    stage = state.get("current_stage", "welcome")
    stages_complete = state.get("stages_complete", {})

    # If current stage NOT complete — stop here, wait for next user message
    if not stages_complete.get(stage, False):
        return END

    # Stage IS complete — advance to next
    progression = {
        "welcome":         "gathering",
        "gathering":       "document_upload",
        "document_upload": "review",
        "review":          "credit_check",
        "credit_check":    "decision",
        "signing":         "onboarding",
        "onboarding":      END,
    }

    if stage == "decision":
        return _route_from_decision(state)

    return progression.get(stage, END)

def _route_from_decision(state: LoanAgentState) -> str:
    outcome = state.get("decision_outcome")
    if outcome == "auto_approve":
        return "signing"
    elif outcome in ("auto_decline", "refer_underwriter"):
        return END
    return END

# ── Build the graph ──────────────────────────────────────────

def build_graph():
    builder = StateGraph(LoanAgentState)

    # Add all stage nodes
    builder.add_node("welcome",        welcome_node)
    builder.add_node("gathering",      gathering_node)
    builder.add_node("document_upload",document_upload_node)
    builder.add_node("review",            review_node)
    builder.add_node("credit_check",      credit_check_node)
    builder.add_node("decision",          decision_node)
    builder.add_node("signing",           signing_node)
    builder.add_node("onboarding",        onboarding_node)
    builder.add_node("handoff_agent",      human_handoff_node)

    # Entry point
    builder.add_node("__router__", lambda s: s)  # passthrough node
    builder.set_entry_point("__router__")
    builder.add_conditional_edges("__router__", entry_router)

    # Conditional routing from every node
    for node in [
        "welcome", "gathering", "document_upload",
        "review", "credit_check", "decision", "signing",
        "onboarding", "handoff_agent"
    ]:
        builder.add_conditional_edges(node, route_after_stage)

    # Compile with in-memory checkpointing (Redis checkpointer can replace this)
    memory = MemorySaver()
    graph = builder.compile(checkpointer=memory, debug=False)
    
    logger.info("✅ LangGraph compiled successfully")
    return graph

# Singleton graph instance
_graph = None

def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph