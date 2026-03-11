"""
Shared utilities for all stage nodes.
Every stage node receives LoanAgentState and returns a partial state update.
"""
import logging
from langchain_core.messages import AIMessage
from agent.state import LoanAgentState
from core.llm import call_llm as _call_llm

logger = logging.getLogger(__name__)

async def call_llm(prompt: str, system: str = None) -> str:
    """Call the configured LLM — Ollama locally, Claude API in cloud."""
    return await _call_llm(prompt, system=system)

async def stub_node(state: LoanAgentState) -> dict:
    """Placeholder for unimplemented stages — returns a holding message."""
    stage = state.get("current_stage", "unknown")
    return {
        "messages": [AIMessage(content=f"[Stage '{stage}' is being built. Stay tuned!]")]
    }
