src/api/store.py

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Event:
    event_id: str
    ts_ms: int
    type: str
    session_id: str
    payload: Dict[str, Any]


class InMemoryEventStore:
    """
    Minimal in-memory store.
    Good enough to power dashboard/insights early.
    Replace later with DB/Redis.

    Added:
      - session-scoped KV for orchestration state (e.g., selected_table)
    """

    def __init__(self, max_events: int = 5000) -> None:
        self.max_events = max_events
        self._events: List[Event] = []
        # Session-scoped context, e.g. {"session_id": {"selected_table": "public.orders"}}
        self._session_kv: Dict[str, Dict[str, Any]] = {}

    def add(self, type: str, session_id: Optional[str], payload: Dict[str, Any]) -> Event:
        ev = Event(
            event_id=str(uuid.uuid4()),
            ts_ms=int(time.time() * 1000),
            type=type,
            session_id=session_id or "default",
            payload=payload,
        )
        self._events.append(ev)
        if len(self._events) > self.max_events:
            self._events = self._events[-self.max_events :]
        return ev

    def list(self, limit: int = 200) -> List[Dict[str, Any]]:
        return [asdict(e) for e in self._events[-limit:]]

    def count(self) -> int:
        return len(self._events)

    def counts_by_type(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in self._events:
            out[e.type] = out.get(e.type, 0) + 1
        return out

    # ---------------------------
    # NEW: session context helpers
    # ---------------------------

    def set_session_value(self, session_id: str, key: str, value: Any) -> None:
        """
        Store session-scoped orchestration state (in-memory).
        This does NOT change any existing behavior.
        """
        sid = session_id or "default"
        if sid not in self._session_kv:
            self._session_kv[sid] = {}
        self._session_kv[sid][key] = value

        # Optional: store an event for observability/debugging
        self.add(
            type="session_context_set",
            session_id=sid,
            payload={"key": key, "value": value},
        )

    def get_session_value(self, session_id: str, key: str, default: Any = None) -> Any:
        sid = session_id or "default"
        return self._session_kv.get(sid, {}).get(key, default)

    def clear_session(self, session_id: str) -> None:
        sid = session_id or "default"
        if sid in self._session_kv:
            del self._session_kv[sid]
        self.add(type="session_context_cleared", session_id=sid, payload={})




------------------

src/api/routes/chat.py



from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException

from src.api.models import ChatRequest, ChatResponse
from src.api.store import InMemoryEventStore

log = logging.getLogger("api.chat")
router = APIRouter(prefix="/api", tags=["chat"])


def get_agents() -> Dict[str, Any]:
    raise RuntimeError("Agents dependency not wired")


def get_store() -> InMemoryEventStore:
    raise RuntimeError("Store dependency not wired")


# -------------------------
# Orchestration: Part 1
# -------------------------

_TABLE_PREFIX_RE = re.compile(
    r"^\s*table\s*=\s*([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\s*\|\s*(.+)$",
    re.DOTALL,
)

# Intent keywords (fast, deterministic routing)
_DQ_KEYWORDS = (
    "duplicate", "duplicates", "null", "missing", "empty", "outlier", "anomaly",
    "invalid", "constraint", "quality", "drift", "profiling", "profile", "freshness",
    "consistency", "uniqueness", "completeness", "accuracy",
)
_ANALYTICS_KEYWORDS = (
    "trend", "growth", "compare", "correlation", "forecast", "rolling", "window",
    "month over month", "mom", "yoy", "year over year", "retention", "cohort",
    "segment", "breakdown", "group by", "join", "funnel", "conversion",
)


def _parse_table_message(message: str) -> Tuple[Optional[str], str]:
    """
    Parses: "table=schema.table | user query"
    Returns: (table, clean_prompt)
    """
    raw = (message or "").strip()
    m = _TABLE_PREFIX_RE.match(raw)
    if not m:
        return None, raw
    return m.group(1).strip(), m.group(2).strip()


def _route_agent(table: Optional[str], prompt: str) -> Tuple[str, str]:
    """
    Production-safe deterministic routing:
      - DQ intent -> agent_3
      - Analytics intent -> agent_2
      - else -> agent_1

    Optional table-based overrides via env (simple string mapping):
      AGENT_TABLE_PREFIX_MAP="order:agent_2,dq_:agent_3"
    """
    p = (prompt or "").lower()

    # Intent-first routing
    if any(k in p for k in _DQ_KEYWORDS):
        return "agent_3", "Intent routing: data-quality keywords detected"
    if any(k in p for k in _ANALYTICS_KEYWORDS):
        return "agent_2", "Intent routing: analytics keywords detected"

    # Optional table-name overrides (lightweight config)
    mapping = os.getenv("AGENT_TABLE_PREFIX_MAP", "").strip()
    if table and mapping:
        try:
            _, name = table.split(".", 1)
        except ValueError:
            name = table
        for pair in mapping.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            prefix, agent = pair.split(":", 1)
            prefix = prefix.strip()
            agent = agent.strip()
            if prefix and agent and name.startswith(prefix):
                return agent, f"Table routing override: table name starts with '{prefix}'"

    return "agent_1", "Default routing"


def _inject_context(prompt: str, selected_table: Optional[str]) -> str:
    """
    Inject compact context for the agent. This does not change /api/chat contract.
    """
    if not selected_table:
        return prompt
    return (
        "[CONTEXT]\n"
        f"selected_table={selected_table}\n"
        "[/CONTEXT]\n\n"
        f"{prompt}"
    )


# -------------------------
# Existing helpers (unchanged)
# -------------------------

def _extract_content(out: Any) -> str:
    """
    Normalize outputs from agents.
    - If it's a RunOutput-like object: return .content
    - If it's dict-like: return common fields
    - Else: str(out)
    """
    if out is None:
        return ""

    if hasattr(out, "content"):
        content = getattr(out, "content")
        return "" if content is None else str(content)

    for attr in ("output", "text", "message"):
        if hasattr(out, attr):
            val = getattr(out, attr)
            if val is not None:
                return str(val)

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

    if hasattr(agent_obj, "run") and callable(agent_obj.run):
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

        out = agent_obj.run(message)
        return _extract_content(out)

    if hasattr(agent_obj, "respond") and callable(agent_obj.respond):
        out = agent_obj.respond(message)
        return _extract_content(out)

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
    requested_agent = req.agent or "agent_1"

    # Keep existing behavior: unknown requested agent => 400
    if requested_agent not in agents:
        raise HTTPException(status_code=400, detail=f"Unknown agent '{requested_agent}'")

    # ✅ guarantee metadata always present
    metadata = req.metadata or {}

    # --- Orchestration ---
    table_from_msg, clean_prompt = _parse_table_message(req.message)

    # Stateful table binding:
    # - if prefix exists, store it
    # - else, try session fallback
    selected_table = table_from_msg
    if selected_table:
        store.set_session_value(session_id, "selected_table", selected_table)
    else:
        selected_table = store.get_session_value(session_id, "selected_table", None)

    # If no table ever selected, we can still run agent_1 to reply with guidance
    if not selected_table:
        routed_agent = "agent_1"
        route_reason = "No table selected for session; asking user to select a table"
        final_prompt = (
            "Please select a table first (UI will send: table=schema.table | your question). "
            "Example: table=public.orders | show top 5 orders"
        )
    else:
        routed_agent, route_reason = _route_agent(selected_table, clean_prompt)
        if routed_agent not in agents:
            # Safety fallback
            routed_agent = "agent_1"
            route_reason = f"{route_reason}; fallback to agent_1 because '{routed_agent}' not registered"
        final_prompt = _inject_context(clean_prompt, selected_table)

    # Enrich metadata for agent + observability (does not change API schema)
    orchestration_meta = {
        "selected_table": selected_table,
        "requested_agent": requested_agent,
        "routed_agent": routed_agent,
        "route_reason": route_reason,
    }
    merged_metadata = {**metadata, **{k: v for k, v in orchestration_meta.items() if v is not None}}

    # Store request event (keep old fields; add routing info)
    store.add(
        type="chat_request",
        session_id=session_id,
        payload={
            "agent": requested_agent,
            "message": req.message,
            "metadata": metadata,
            "orchestration": orchestration_meta,
        },
    )
    log.info(
    "Orchestration | session=%s | requested=%s | routed=%s | table=%s | reason=%s",
    session_id,
    requested_agent,
    routed_agent,
    selected_table,
    route_reason,
)
    try:
        reply = _call_agent(agents[routed_agent], final_prompt, session_id, merged_metadata)
    except Exception as e:
        log.exception("Agent call failed")
        store.add(
            type="chat_error",
            session_id=session_id,
            payload={
                "agent": routed_agent,
                "requested_agent": requested_agent,
                "error": str(e),
                "orchestration": orchestration_meta,
            },
        )
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {e}")

    store.add(
        type="chat_response",
        session_id=session_id,
        payload={
            "agent": requested_agent,      # keep outward semantics stable
            "routed_agent": routed_agent,  # internal truth
            "reply": reply,
            "orchestration": orchestration_meta,
        },
    )

    # IMPORTANT: response contract unchanged
    return ChatResponse(session_id=session_id, agent=requested_agent, reply=reply, raw={})

