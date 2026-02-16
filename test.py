from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from src.api.models import ChatRequest, ChatResponse
from src.api.store import InMemoryEventStore

log = logging.getLogger("api.chat")
router = APIRouter(prefix="/api", tags=["chat"])


def get_agents() -> Dict[str, Any]:
    raise RuntimeError("Agents dependency not wired")


def get_store() -> InMemoryEventStore:
    raise RuntimeError("Store dependency not wired")


def _extract_content(out: Any) -> str:
    """
    Normalize outputs from agents.
    - If it's a RunOutput-like object: return .content
    - If it's dict-like: return common fields
    - Else: str(out)
    """
    if out is None:
        return ""

    # RunOutput / dataclass / object with 'content'
    if hasattr(out, "content"):
        content = getattr(out, "content")
        return "" if content is None else str(content)

    # Some libs use 'output' or 'text'
    for attr in ("output", "text", "message"):
        if hasattr(out, attr):
            val = getattr(out, attr)
            if val is not None:
                return str(val)

    # Dict-like outputs
    if isinstance(out, dict):
        for key in ("content", "reply", "text", "message", "output"):
            if key in out and out[key] is not None:
                return str(out[key])
        return str(out)

    return str(out)


def _call_agent(agent_obj: Any, message: str, session_id: str, metadata: Dict[str, Any]) -> str:
    """
    Flexible agent caller:
    - run(input=..., metadata=...)
    - run(message=..., metadata=...)
    - run(positional)
    - respond(positional)
    - __call__(...)
    Always passes metadata (defaults to {}).
    """
    metadata = metadata or {}

    # run()
    if hasattr(agent_obj, "run") and callable(agent_obj.run):
        # Try common kw patterns
        for kwargs in (
            {"input": message, "session_id": session_id, "metadata": metadata},
            {"message": message, "session_id": session_id, "metadata": metadata},
            {"input": message, "metadata": metadata},
            {"message": message, "metadata": metadata},
        ):
            try:
                out = agent_obj.run(**kwargs)
                return _extract_content(out)
            except TypeError:
                pass

        # Fallback: positional
        out = agent_obj.run(message)
        return _extract_content(out)

    # respond()
    if hasattr(agent_obj, "respond") and callable(agent_obj.respond):
        out = agent_obj.respond(message)
        return _extract_content(out)

    # callable agent
    if callable(agent_obj):
        for kwargs in (
            {"input": message, "session_id": session_id, "metadata": metadata},
            {"message": message, "session_id": session_id, "metadata": metadata},
            {"input": message, "metadata": metadata},
            {"message": message, "metadata": metadata},
        ):
            try:
                out = agent_obj(**kwargs)
                return _extract_content(out)
            except TypeError:
                pass

        out = agent_obj(message)
        return _extract_content(out)

    raise TypeError(f"Agent {type(agent_obj).__name__} has no callable interface (run/respond/__call__).")


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    agents: Dict[str, Any] = Depends(get_agents),
    store: InMemoryEventStore = Depends(get_store),
) -> ChatResponse:
    session_id = req.session_id or "default"
    agent_key = req.agent or "agent_1"

    if agent_key not in agents:
        raise HTTPException(status_code=400, detail=f"Unknown agent '{agent_key}'")

    # ✅ guarantee metadata always present
    metadata = req.metadata or {}

    store.add(
        type="chat_request",
        session_id=session_id,
        payload={"agent": agent_key, "message": req.message, "metadata": metadata},
    )

    try:
        reply = _call_agent(agents[agent_key], req.message, session_id, metadata)
    except Exception as e:
        log.exception("Agent call failed")
        store.add(
            type="chat_error",
            session_id=session_id,
            payload={"agent": agent_key, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {e}")

    store.add(
        type="chat_response",
        session_id=session_id,
        payload={"agent": agent_key, "reply": reply},
    )

    return ChatResponse(session_id=session_id, agent=agent_key, reply=reply, raw={})
