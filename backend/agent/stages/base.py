"""
Shared utilities for all stage nodes.
Every stage node receives LoanAgentState and returns a partial state update.
"""
import logging
import httpx
from langchain_core.messages import AIMessage
from agent.state import LoanAgentState
from core.config import get_settings

logger = logging.getLogger(__name__)

async def call_llm(prompt: str, system: str = None) -> str:
    """Direct Ollama call — returns response text."""
    settings = get_settings()
    payload = {
        "model":  settings.ollama_model,
        "prompt": prompt + " /no_think",  # disable qwen3 thinking mode
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 4096}

    }
    if system:
        payload["system"] = system

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/generate",
            json=payload
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

async def stub_node(state: LoanAgentState) -> dict:
    """Placeholder for unimplemented stages — returns a holding message."""
    stage = state.get("current_stage", "unknown")
    return {
        "messages": [AIMessage(content=f"[Stage '{stage}' is being built. Stay tuned!]")]
    }
