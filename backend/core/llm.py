"""
LLM abstraction — supports Ollama (local) and Claude API (cloud).
Controlled by the LLM_PROVIDER env var: "ollama" (default) or "claude".
"""
import logging
import httpx
from core.config import get_settings

logger = logging.getLogger(__name__)


async def call_llm(prompt: str, system: str = None, temperature: float = 0.3) -> str:
    """
    Call the configured LLM and return the response text.
    Local dev:  LLM_PROVIDER=ollama  → hits Ollama at OLLAMA_BASE_URL
    Cloud:      LLM_PROVIDER=claude  → hits Anthropic API
    """
    settings = get_settings()

    if settings.llm_provider == "claude":
        return await _call_claude(prompt, system, temperature, settings)
    else:
        return await _call_ollama(prompt, system, temperature, settings)


async def _call_ollama(prompt: str, system: str, temperature: float, settings) -> str:
    payload = {
        "model":   settings.ollama_model,
        "prompt":  prompt + " /no_think",
        "stream":  False,
        "options": {"temperature": temperature, "num_predict": 4096},
    }
    if system:
        payload["system"] = system

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/generate",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()


async def _call_claude(prompt: str, system: str, temperature: float, settings) -> str:
    import anthropic

    messages = [{"role": "user", "content": prompt}]
    kwargs = {
        "model":      settings.claude_model,
        "max_tokens": 4096,
        "temperature": temperature,
        "messages":   messages,
    }
    if system:
        kwargs["system"] = system

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(**kwargs)
    return response.content[0].text.strip()
