# src/api/routes/chat.py
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from agno.team import Team

from src.api.deps import get_store, get_team
from src.api.models import ChatRequest, ChatResponse
from src.api.store import InMemoryEventStore
from src.api.orchestrator_team import extract_agent_used

log = logging.getLogger("api.chat")
router = APIRouter(prefix="/api", tags=["chat"])


# Matches:
# ```json
# {...}
# ```
# or
# ```echarts
# {...}
# ```
_FENCE_RE = re.compile(r"```(?:json|echarts)\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _inject_context(user_query: str, selected_table: Optional[str]) -> str:
    if not selected_table:
        return user_query
    return (
        "[CONTEXT]\n"
        f"selected_table={selected_table}\n"
        "[/CONTEXT]\n\n"
        f"{user_query}"
    )


def _safe_str(x: Any) -> str:
    try:
        return "" if x is None else str(x)
    except Exception:
        return ""


def _extract_text_from_any(out: Any) -> str:
    """
    Robust extraction across Agno versions and different return shapes.
    Goal: return the best human-readable text we can find.
    """
    if out is None:
        return ""

    # 1) Common: out.content
    if hasattr(out, "content"):
        c = getattr(out, "content", None)
        if isinstance(c, str) and c.strip():
            return c
        if isinstance(c, dict):
            # Try typical keys
            for k in ("reply", "text", "message", "output", "content"):
                v = c.get(k)
                if isinstance(v, str) and v.strip():
                    return v
            # If dict only, stringify it (so reply isn't empty)
            return json.dumps(c, ensure_ascii=False)

        if c is not None:
            s = _safe_str(c)
            if s.strip():
                return s

    # 2) Other common attributes
    for attr in ("output", "text", "message", "reply"):
        if hasattr(out, attr):
            v = getattr(out, attr, None)
            if isinstance(v, str) and v.strip():
                return v

    # 3) messages list patterns
    if hasattr(out, "messages"):
        msgs = getattr(out, "messages", None)
        if isinstance(msgs, list) and msgs:
            last = msgs[-1]
            if isinstance(last, str) and last.strip():
                return last
            if isinstance(last, dict):
                for k in ("content", "text", "message"):
                    v = last.get(k)
                    if isinstance(v, str) and v.strip():
                        return v
                # stringify dict message
                return json.dumps(last, ensure_ascii=False)
            s = _safe_str(last)
            if s.strip():
                return s

    # 4) Last resort: stringify the whole object
    s = _safe_str(out)
    return s


def _extract_graph_from_fence(text: str) -> Tuple[str, Optional[str]]:
    """
    Extract JSON from a fenced block (```json or ```echarts).
    Returns:
      clean_text: text with the fenced block removed
      graph_json_str: JSON string (not dict) or None
    """
    if not text or not text.strip():
        return text, None

    m = _FENCE_RE.search(text)
    if not m:
        return text, None

    blob = (m.group(1) or "").strip()
    if not blob:
        return _FENCE_RE.sub("", text).strip(), None

    # Try to validate JSON; if it isn't clean JSON, try to locate first {...} or [...]
    candidate = blob
    try:
        json.loads(candidate)
    except Exception:
        m2 = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", blob)
        if m2:
            candidate = m2.group(1).strip()
            try:
                json.loads(candidate)
            except Exception:
                # Still return raw blob as string; better than losing it
                candidate = blob

    clean_text = _FENCE_RE.sub("", text).strip()
    return clean_text, candidate


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    team: Team = Depends(get_team),
    store: InMemoryEventStore = Depends(get_store),
) -> ChatResponse:
    session_id = req.session_id or "default"
    metadata: Dict[str, Any] = req.metadata or {}

    table_name = (req.table_name or "").strip() if req.table_name else None
    user_query = (req.user_query or "").strip() if req.user_query else None

    # Backward compatibility: message (deprecated)
    if not (table_name and user_query):
        if req.message:
            store.add(
                type="chat_request_legacy",
                session_id=session_id,
                payload={"message": req.message, "metadata": metadata},
            )
            raise HTTPException(
                status_code=400,
                detail="Legacy request detected. Please use: table_name + user_query (+ session_id).",
            )
        raise HTTPException(status_code=400, detail="Provide table_name and user_query")

    # Session-scoped table binding
    store.set_session_value(session_id, "selected_table", table_name)
    selected_table = store.get_session_value(session_id, "selected_table", None)

    if not selected_table:
        guidance = (
            "No table is selected for this session. Please send a table_name.\n"
            "Example: table_name=public.orders, user_query='show top 5 orders'"
        )
        store.add(type="chat_response", session_id=session_id, payload={"agent_used": "none", "reply": guidance})
        return ChatResponse(session_id=session_id, agent_used="none", reply=guidance, structured_output=None, raw={})

    final_prompt = _inject_context(user_query, selected_table)

    store.add(
        type="chat_request",
        session_id=session_id,
        payload={"table_name": selected_table, "user_query": user_query, "metadata": metadata},
    )

    try:
        out = team.run(input=final_prompt, session_id=session_id)
        agent_used = extract_agent_used(out)

        # 1) Extract the best possible text
        raw_text = _extract_text_from_any(out)

        # 2) Pull out graph JSON if present (```echarts / ```json)
        clean_text, graph_json_str = _extract_graph_from_fence(raw_text)

        # 3) Ensure reply is not empty
        reply = clean_text.strip()
        if not reply:
            # If the model returned only a graph block, give a fallback message
            if graph_json_str:
                reply = "Generated chart JSON."
            else:
                # Truly empty: still return something for Swagger/debug
                reply = raw_text.strip() or "No response text returned."

        structured_output = None
        if graph_json_str and graph_json_str.strip():
            structured_output = {"graph_json": graph_json_str}

        # Helpful console logs while testing in Swagger
        log.info(
            "Orchestration | session=%s | table=%s | agent_used=%s | has_graph=%s | reply_len=%s",
            session_id,
            selected_table,
            agent_used,
            bool(structured_output),
            len(reply),
        )

        # Store full debug info for later dashboard/insights
        store.add(
            type="chat_response",
            session_id=session_id,
            payload={
                "agent_used": agent_used,
                "reply": reply,
                "structured_output": structured_output,
                "table_name": selected_table,
                # Keep the raw extracted text for debugging
                "raw_text": raw_text,
            },
        )

        return ChatResponse(
            session_id=session_id,
            agent_used=agent_used or "unknown",
            reply=reply,
            structured_output=structured_output,
            raw={
                "selected_table": selected_table,
                "metadata": metadata,
            },
        )

    except Exception as e:
        log.exception("Team execution failed")
        store.add(
            type="chat_error",
            session_id=session_id,
            payload={"error": str(e), "table_name": selected_table, "user_query": user_query},
        )
        raise HTTPException(status_code=500, detail=f"Orchestrator execution failed: {e}")
