# src/api/models.py
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, root_validator


class ChatRequest(BaseModel):
    """
    Swagger-friendly contract:
      - table_name: selected table from UI
      - user_query: user's natural language query
      - session_id: stateful response key

    Backward compatibility:
      - If older clients still send `message`, we accept it but prefer table_name/user_query.
    """
    table_name: Optional[str] = Field(
        default=None,
        description="Selected table name, e.g., public.orders",
        min_length=1,
    )
    user_query: Optional[str] = Field(
        default=None,
        description="Natural language question from user",
        min_length=1,
    )

    # Backward compatible (old contract)
    message: Optional[str] = Field(
        default=None,
        description="(Deprecated) old field. Prefer table_name + user_query.",
    )

    session_id: Optional[str] = Field(default=None, description="Session id for stateful runs")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @root_validator(pre=True)
    def _validate_inputs(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        # If table_name/user_query provided, OK.
        table_name = (values.get("table_name") or "").strip() if values.get("table_name") else None
        user_query = (values.get("user_query") or "").strip() if values.get("user_query") else None
        message = (values.get("message") or "").strip() if values.get("message") else None

        if table_name and user_query:
            values["table_name"] = table_name
            values["user_query"] = user_query
            return values

        # Backward compatibility:
        # If only message is provided, allow it (chat route can guide user / parse legacy format)
        if message:
            values["message"] = message
            return values

        raise ValueError("Provide either (table_name + user_query) OR message")

    class Config:
        schema_extra = {
            "example": {
                "table_name": "public.orders",
                "user_query": "Show top 5 customers by total spend in last 30 days",
                "session_id": "abc123",
                "metadata": {"source": "swagger"},
            }
        }


class ChatResponse(BaseModel):
    session_id: str
    agent_used: str
    reply: str
    raw: Dict[str, Any] = Field(default_factory=dict)


class DashboardSummary(BaseModel):
    status: str
    agents: Dict[str, str]
    total_events: int
    events_by_type: Dict[str, int]


class InsightsOverview(BaseModel):
    total_events: int
    events_by_type: Dict[str, int]
    recent_events: list

--------------------------------------------------------------------

# src/api/orchestrator_team.py
from __future__ import annotations

import importlib
import os
from typing import Any, Callable, Optional, Tuple

from agno.team import Team
from agno.team.mode import TeamMode
from agno.models.openai import OpenAIChat

# -------------------------------------------------------------------
# Robust agent loader:
# - tries multiple attribute names from each src.agents.agent_X module
# - supports: class / factory fn / already-instantiated agent
# -------------------------------------------------------------------

_AGENT_ATTR_CANDIDATES = (
    # common class names
    "Agent1", "Agent2", "Agent3",
    # common factory names
    "first_agent", "second_agent", "third_agent",
    "build_agent", "get_agent", "create_agent",
    # generic
    "agent",
)

def _load_agent_from_module(module_path: str) -> Any:
    mod = importlib.import_module(module_path)

    # Try common attribute candidates first
    for attr in _AGENT_ATTR_CANDIDATES:
        if hasattr(mod, attr):
            obj = getattr(mod, attr)
            return _instantiate_if_needed(obj)

    # Fallback: scan module globals for something agent-like
    for name, obj in vars(mod).items():
        if name.startswith("_"):
            continue
        # heuristics: if it has run/respond/print_response, assume agent
        if hasattr(obj, "run") or hasattr(obj, "respond") or hasattr(obj, "print_response"):
            return _instantiate_if_needed(obj)

    raise RuntimeError(
        f"Could not find an agent factory/class/object in module '{module_path}'. "
        f"Expected one of: {', '.join(_AGENT_ATTR_CANDIDATES)}"
    )

def _instantiate_if_needed(obj: Any) -> Any:
    # If it's a class, instantiate
    if isinstance(obj, type):
        return obj()
    # If it's a callable factory function, call it (but not if it's already an agent instance)
    if callable(obj) and not (hasattr(obj, "run") or hasattr(obj, "respond") or hasattr(obj, "print_response")):
        return obj()
    # Otherwise assume it's already an agent instance
    return obj


def build_default_team() -> Team:
    """
    Builds a routing team using your existing agents in:
      src.agents.agent_1
      src.agents.agent_2
      src.agents.agent_3

    Uses TeamMode.route so leader routes to ONE member and returns that member's response.

    IMPORTANT:
    - We keep determine_input_for_members=False so the leader doesn't rewrite your prompt.
    - store_member_responses=True so we can extract agent_used reliably.
    """
    agent1 = _load_agent_from_module("src.agents.agent_1")
    agent2 = _load_agent_from_module("src.agents.agent_2")
    agent3 = _load_agent_from_module("src.agents.agent_3")

    model_id = os.getenv("AGNO_TEAM_MODEL_ID", "gpt-4o")
    team_model = OpenAIChat(id=model_id)

    team = Team(
        name="Chat Orchestrator Team",
        description="Routes user query to the best specialized agent and returns member output directly.",
        model=team_model,
        members=[agent1, agent2, agent3],
        mode=TeamMode.route,
        determine_input_for_members=False,      # passthrough prompt
        store_member_responses=True,            # needed to know agent_used
        show_members_responses=True,            # prints member logs (useful while testing in swagger)
        debug_mode=True,
        debug_level=1,
        instructions=[
            "You are an orchestrator. Your job is ONLY to pick the best member agent and delegate.",
            "Choose exactly one member agent. Do not answer yourself.",
            "Use the selected_table and user_query to decide.",
            "Return the member agent's response directly.",
        ],
    )
    return team


def extract_agent_used(team_run_output: Any) -> str:
    """
    Best-effort extraction of which member handled the request.

    In route mode + store_member_responses=True, team_run_output.member_responses
    should contain the delegated member RunOutput, which includes agent_name.
    """
    try:
        member_responses = getattr(team_run_output, "member_responses", None)
        if member_responses:
            # Route mode usually delegates to exactly one member
            mr0 = member_responses[0]
            # RunOutput reference includes agent_name
            agent_name = getattr(mr0, "agent_name", None) or getattr(mr0, "agent_id", None)
            if agent_name:
                return str(agent_name)
    except Exception:
        pass

    # Fallback: try events (if stored/available)
    try:
        events = getattr(team_run_output, "events", None)
        if events:
            # find last event with agent_name populated
            for ev in reversed(events):
                an = getattr(ev, "agent_name", None)
                if an:
                    return str(an)
    except Exception:
        pass

    return "unknown"
---------------------------------------------------------------------------------------------

# src/api/deps.py
from __future__ import annotations

from typing import Optional

from agno.team import Team

from src.api.store import InMemoryEventStore
from src.api.orchestrator_team import build_default_team

_store: Optional[InMemoryEventStore] = None
_team: Optional[Team] = None


def init_api_dependencies(store: InMemoryEventStore, team: Team) -> None:
    """
    Allow app_factory/main to inject singletons explicitly.
    """
    global _store, _team
    _store = store
    _team = team


def get_store() -> InMemoryEventStore:
    global _store
    if _store is None:
        _store = InMemoryEventStore()
    return _store


def get_team() -> Team:
    global _team
    if _team is None:
        _team = build_default_team()
    return _team
------------------------------------------------

# src/api/routes/chat.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from agno.team import Team

from src.api.models import ChatRequest, ChatResponse
from src.api.store import InMemoryEventStore
from src.api.deps import get_store, get_team
from src.api.orchestrator_team import extract_agent_used

log = logging.getLogger("api.chat")
router = APIRouter(prefix="/api", tags=["chat"])


def _inject_context(user_query: str, selected_table: Optional[str]) -> str:
    if not selected_table:
        return user_query
    return (
        "[CONTEXT]\n"
        f"selected_table={selected_table}\n"
        "[/CONTEXT]\n\n"
        f"{user_query}"
    )


def _extract_team_content(out: Any) -> str:
    if out is None:
        return ""
    if hasattr(out, "content"):
        c = getattr(out, "content")
        return "" if c is None else str(c)
    return str(out)


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    team: Team = Depends(get_team),
    store: InMemoryEventStore = Depends(get_store),
) -> ChatResponse:
    session_id = req.session_id or "default"
    metadata: Dict[str, Any] = req.metadata or {}

    # --- Determine table + query ---
    # New contract (preferred)
    table_name = (req.table_name or "").strip() if req.table_name else None
    user_query = (req.user_query or "").strip() if req.user_query else None

    # Backward compatibility (old contract)
    if not (table_name and user_query):
        # If message provided, we can only proceed if it contains a usable intent.
        # Since you asked Swagger to use explicit fields, we guide the user.
        if req.message:
            msg = req.message.strip()
            store.add(
                type="chat_request_legacy",
                session_id=session_id,
                payload={"message": msg, "metadata": metadata},
            )
            raise HTTPException(
                status_code=400,
                detail="Legacy request detected. Please use: table_name + user_query (+ session_id).",
            )
        raise HTTPException(status_code=400, detail="Provide table_name and user_query")

    # Session-scoped table binding (so frontend can send table_name once then omit later if desired)
    if table_name:
        store.set_session_value(session_id, "selected_table", table_name)
    selected_table = store.get_session_value(session_id, "selected_table", None)

    if not selected_table:
        # Still allow orchestrator to respond with guidance
        guidance = (
            "No table is selected for this session. Please send a table_name.\n"
            "Example: table_name=public.orders, user_query='show top 5 orders'"
        )
        store.add(type="chat_response", session_id=session_id, payload={"agent_used": "none", "reply": guidance})
        return ChatResponse(session_id=session_id, agent_used="none", reply=guidance, raw={})

    final_prompt = _inject_context(user_query, selected_table)

    # Observability event
    store.add(
        type="chat_request",
        session_id=session_id,
        payload={
            "table_name": selected_table,
            "user_query": user_query,
            "metadata": metadata,
        },
    )

    # Run Team (Agno is the orchestrator)
    try:
        # Team.run supports session_id parameter :contentReference[oaicite:4]{index=4}
        out = team.run(input=final_prompt, session_id=session_id)
        reply = _extract_team_content(out)
        agent_used = extract_agent_used(out)
    except Exception as e:
        log.exception("Team execution failed")
        store.add(
            type="chat_error",
            session_id=session_id,
            payload={"error": str(e), "table_name": selected_table, "user_query": user_query},
        )
        raise HTTPException(status_code=500, detail=f"Orchestrator execution failed: {e}")

    # Log to console (helps during Swagger testing)
    log.info(
        "Orchestration | session=%s | table=%s | agent_used=%s",
        session_id,
        selected_table,
        agent_used,
    )

    store.add(
        type="chat_response",
        session_id=session_id,
        payload={
            "agent_used": agent_used,
            "reply": reply,
            "table_name": selected_table,
        },
    )

    return ChatResponse(
        session_id=session_id,
        agent_used=agent_used,
        reply=reply,
        raw={
            "selected_table": selected_table,
            "metadata": metadata,
        },
    )
------------------------------------------------------
# backend/api/app_factory.py
from __future__ import annotations

from fastapi import FastAPI

from src.api.deps import init_api_dependencies
from src.api.store import InMemoryEventStore
from src.api.orchestrator_team import build_default_team

from src.api.routes.chat import router as chat_router
# keep these imports even if routes not used yet
from src.api.routes.dashboard import router as dashboard_router  # noqa
from src.api.routes.insights import router as insights_router  # noqa


def create_app() -> FastAPI:
    app = FastAPI(title="Agno AgentOS Backend", version="0.1.0")

    # Build dependencies once
    store = InMemoryEventStore()
    team = build_default_team()

    # Register into deps singletons
    init_api_dependencies(store=store, team=team)

    # Include routers
    app.include_router(chat_router)
    app.include_router(dashboard_router)
    app.include_router(insights_router)

    return app
