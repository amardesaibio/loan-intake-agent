"""
Chat API - SSE streaming endpoint.
Redis is the single source of truth for session state.
"""
import json
import uuid
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage

from agent.graph import get_graph
from agent.state import initial_state, STAGE_LABELS
from core.config import get_settings
from core.redis_client import (
    get_session, set_session, update_session,
    append_message, get_history
)
from langfuse.callback import CallbackHandler as LangfuseCallbackHandler

logger = logging.getLogger(__name__)
router = APIRouter()


class StartSessionRequest(BaseModel):
    session_id: str = None


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str


class HumanHandoffRequest(BaseModel):
    session_id: str
    reason: str = "Customer requested human assistance"


@router.post("/session/start")
async def start_session(req: StartSessionRequest):
    session_id = req.session_id or str(uuid.uuid4())
    existing = await get_session(session_id)
    if existing:
        return {
            "session_id":  session_id,
            "stage":       existing.get("current_stage", "welcome"),
            "stage_label": STAGE_LABELS.get(existing.get("current_stage", "welcome")),
            "resumed":     True
        }
    state = initial_state(session_id)
    await set_session(session_id, {
        "current_stage":   "welcome",
        "stages_complete": state["stages_complete"],
        "applicant_data":  {},
        "human_handoff":   False,
    })
    logger.info(f"New session started: {session_id}")
    return {
        "session_id":  session_id,
        "stage":       "welcome",
        "stage_label": STAGE_LABELS["welcome"],
        "resumed":     False
    }


@router.post("/message")
async def send_message(req: ChatMessageRequest):
    """
    State strategy:
    - Redis is the single source of truth for stage + applicant_data
    - On every request, full state is rebuilt from Redis + history
    - After streaming, final state is written back to Redis
    """
    session = await get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Call /session/start first.")
    if session.get("human_handoff"):
        raise HTTPException(status_code=400, detail="Session is in human handoff mode.")

    async def event_stream():
        try:
            await append_message(req.session_id, "user", req.message)
            yield _sse_event("status", {"type": "typing", "message": "..."})

            # Rebuild full state from Redis (single source of truth)
            state_values = initial_state(req.session_id)
            state_values["current_stage"]     = session.get("current_stage", "welcome")
            state_values["stages_complete"]    = session.get("stages_complete", state_values["stages_complete"])
            state_values["applicant_data"]     = session.get("applicant_data", {})
            state_values["applicant_id"]        = session.get("applicant_id")
            state_values["application_id"]     = session.get("application_id")
            state_values["application_number"] = session.get("application_number")
            state_values["credit_result"]      = session.get("credit_result")
            state_values["documents_uploaded"] = session.get("documents_uploaded", [])
            state_values["decision_outcome"]   = session.get("decision_outcome")
            state_values["envelope_id"]        = session.get("envelope_id")
            state_values["signing_url"]        = session.get("signing_url")
            state_values["document_signed"]    = session.get("document_signed", False)

            # Rebuild conversation history from Redis
            history = await get_history(req.session_id)
            messages = []
            for h in history[:-1]:  # exclude message we just appended
                if h["role"] == "user":
                    messages.append(HumanMessage(content=h["content"]))
                elif h["role"] == "assistant":
                    messages.append(AIMessage(content=h["content"]))
            messages.append(HumanMessage(content=req.message))
            state_values["messages"] = messages

            logger.info(
                f"Session {req.session_id}: stage={state_values['current_stage']} "
                f"history_len={len(messages)} "
                f"data_keys={list(state_values['applicant_data'].keys())}"
            )

            graph = get_graph()
            settings = get_settings()
            langfuse_handler = LangfuseCallbackHandler(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
                session_id=req.session_id,
                user_id=req.session_id,
                trace_name=f"loan-agent/{state_values['current_stage']}",
            )
            config = {
                "configurable": {"thread_id": req.session_id},
                "recursion_limit": 50,
                "callbacks": [langfuse_handler],
            }
            full_response = ""
            last_saved_response = None
            last_chunk = {}

            async for chunk in graph.astream(state_values, config=config, stream_mode="values"):
                last_chunk = chunk

                msgs = chunk.get("messages", [])
                if msgs:
                    last = msgs[-1]
                    if hasattr(last, "content") and last.type == "ai":
                        content = last.content
                        if content:
                            if content.startswith(full_response):
                                # Continuation of current streaming message
                                delta = content[len(full_response):]
                                if delta:
                                    full_response = content
                                    yield _sse_event("token", {"text": delta})
                            else:
                                # New message from a chained node — flush previous
                                if full_response:
                                    await append_message(req.session_id, "assistant", full_response)
                                    last_saved_response = full_response
                                    yield _sse_event("message_end", {})
                                full_response = content
                                yield _sse_event("token", {"text": content})

                new_stage = chunk.get("current_stage")
                if new_stage and new_stage != session.get("current_stage"):
                    yield _sse_event("stage_change", {
                        "stage":       new_stage,
                        "stage_label": STAGE_LABELS.get(new_stage, new_stage),
                        "progress":    _stage_progress(new_stage)
                    })

                tool = chunk.get("last_tool_called")
                if tool:
                    yield _sse_event("tool_call", {"tool": tool, "status": "running"})

                decision = chunk.get("decision_outcome")
                if decision:
                    yield _sse_event("decision", {"outcome": decision, "details": chunk.get("decision_details", {})})

                signing_url = chunk.get("signing_url")
                if signing_url:
                    yield _sse_event("signing_url", {"url": signing_url})

                if chunk.get("human_handoff"):
                    yield _sse_event("human_handoff", {"reason": chunk.get("handoff_reason")})

            if full_response and full_response != last_saved_response:
                await append_message(req.session_id, "assistant", full_response)

            if last_chunk:
                await update_session(req.session_id, {
                    "current_stage":      last_chunk.get("current_stage"),
                    "stages_complete":    last_chunk.get("stages_complete", {}),
                    "applicant_data":     last_chunk.get("applicant_data", {}),
                    "applicant_id":       last_chunk.get("applicant_id"),
                    "application_id":     last_chunk.get("application_id"),
                    "application_number": last_chunk.get("application_number"),
                    "human_handoff":      last_chunk.get("human_handoff", False),
                    "decision_outcome":   last_chunk.get("decision_outcome"),
                    "credit_result":      last_chunk.get("credit_result"),
                    "envelope_id":        last_chunk.get("envelope_id"),
                    "signing_url":        last_chunk.get("signing_url"),
                    "document_signed":    last_chunk.get("document_signed", False),
                })
                logger.info(
                    f"Session {req.session_id} saved - "
                    f"stage: {last_chunk.get('current_stage')} "
                    f"data_keys: {list(last_chunk.get('applicant_data', {}).keys())}"
                )
            else:
                logger.warning(f"Session {req.session_id}: no chunks received, Redis not updated")

            yield _sse_event("done", {"session_id": req.session_id})

        except Exception as e:
            logger.error(f"Stream error for session {req.session_id}: {e}", exc_info=True)
            yield _sse_event("error", {"message": "Something went wrong. Please try again."})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/handoff")
async def request_human_handoff(req: HumanHandoffRequest):
    session = await get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await update_session(req.session_id, {"human_handoff": True, "handoff_reason": req.reason})
    history = await get_history(req.session_id)
    transcript = "\n".join([f"[{m['role'].upper()}]: {m['content']}" for m in history[-20:]])
    logger.info(f"Human handoff requested for session {req.session_id}: {req.reason}")
    return {
        "status":             "handoff_initiated",
        "message":            "A loan specialist will contact you within 2 business hours.",
        "reference":          req.session_id[:8].upper(),
        "transcript_preview": transcript[:500]
    }


@router.get("/session/{session_id}")
async def get_session_status(session_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id":         session_id,
        "current_stage":      session.get("current_stage"),
        "stage_label":        STAGE_LABELS.get(session.get("current_stage", "welcome")),
        "progress_pct":       _stage_progress(session.get("current_stage", "welcome")),
        "application_number": session.get("application_number"),
        "human_handoff":      session.get("human_handoff", False),
        "decision_outcome":   session.get("decision_outcome"),
    }


@router.get("/history/{session_id}")
async def get_chat_history(session_id: str):
    history = await get_history(session_id)
    return {"session_id": session_id, "messages": history}


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stage_progress(stage: str) -> int:
    stages = [
        "welcome", "gathering", "document_upload",
        "review", "credit_check", "decision", "signing",
        "onboarding", "complete"
    ]
    try:
        idx = stages.index(stage)
        return round((idx / (len(stages) - 1)) * 100)
    except ValueError:
        return 0