# src/api/app_factory.py
from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from agno.utils.log import log_debug, log_error

from src.api.deps import init_api_dependencies
from src.api.routes.chat import router as chat_router


def create_app(
    base_app: FastAPI | None = None,
    store=None,
    team=None,
) -> FastAPI:
    """
    Mount API routes and attach middleware + global error handlers
    onto existing AgentOS base_app.
    """

    app = base_app

    # --- Dependency wiring (already created externally) ---
    init_api_dependencies(store=store, team=team)

    # --- Request tracing middleware ---
    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id

        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as e:
            log_error(f"Unhandled exception in middleware request_id={request_id}: {e}")
            raise
        finally:
            dt_ms = int((time.perf_counter() - t0) * 1000)
            log_debug(
                f"HTTP request_complete request_id={request_id} "
                f"method={request.method} path={request.url.path} latency_ms={dt_ms}"
            )

        response.headers["x-request-id"] = request_id
        return response

    # --- Global validation error handler ---
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", "unknown")
        log_error(f"HTTP validation_error request_id={request_id}: {exc}")
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "type": "validation_error",
                    "message": "Invalid request payload",
                    "request_id": request_id,
                }
            },
        )

    # --- Global unhandled exception handler ---
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        log_error(f"HTTP unhandled_exception request_id={request_id}: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": "internal_error",
                    "message": "Internal server error",
                    "request_id": request_id,
                }
            },
        )

    # --- Mount routers ---
    app.include_router(chat_router)

    return app

---------------

# src/api/routes/chat.py
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from agno.team import Team
from agno.utils.log import log_debug, log_error

from src.api.models import ChatRequest, ChatResponse
from src.api.store import InMemoryEventStore
from src.api.deps import get_store, get_team
from src.api.orchestrator_team import extract_agent_used

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


def _fallback_member(team: Team) -> Any:
    """
    Safe fallback: use first member if available.
    We keep this deterministic and simple for prod stability.
    """
    members = getattr(team, "members", None) or []
    if not members:
        return None
    return members[0]


def _call_member(member: Any, prompt: str, session_id: str) -> str:
    """
    Best-effort call on a Team member agent without assuming interface.
    """
    if member is None:
        return ""

    if hasattr(member, "run") and callable(member.run):
        try:
            out = member.run(input=prompt, session_id=session_id)
            return _extract_team_content(out)
        except TypeError:
            out = member.run(prompt)
            return _extract_team_content(out)

    if hasattr(member, "respond") and callable(member.respond):
        out = member.respond(prompt)
        return _extract_team_content(out)

    if callable(member):
        out = member(prompt)
        return _extract_team_content(out)

    return ""


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    request: Request,
    team: Team = Depends(get_team),
    store: InMemoryEventStore = Depends(get_store),
) -> ChatResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    session_id = req.session_id or "default"
    metadata: Dict[str, Any] = req.metadata or {}

    # New contract
    table_name = (req.table_name or "").strip() if req.table_name else None
    user_query = (req.user_query or "").strip() if req.user_query else None

    # Backward compatible: if only message provided, reject with guidance
    if not (table_name and user_query):
        if req.message:
            store.add(
                type="chat_request_legacy",
                session_id=session_id,
                payload={"message": req.message.strip(), "metadata": metadata, "request_id": request_id},
            )
            raise HTTPException(
                status_code=400,
                detail="Legacy request detected. Please use: table_name + user_query (+ session_id).",
            )
        raise HTTPException(status_code=400, detail="Provide table_name and user_query")

    # Session-scoped table binding
    if table_name:
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

    # --- request start log ---
    log_debug(
        f"CHAT request_start request_id={request_id} session_id={session_id} "
        f"table={selected_table} user_query_preview='{user_query[:120]}'"
    )

    store.add(
        type="chat_request",
        session_id=session_id,
        payload={
            "request_id": request_id,
            "table_name": selected_table,
            "user_query": user_query,
            "metadata": metadata,
        },
    )

    t0 = time.perf_counter()

    # --- Run Team (Agno orchestrator) ---
    try:
        log_debug(f"CHAT team_run_start request_id={request_id} session_id={session_id}")
        out = team.run(input=final_prompt, session_id=session_id)
        reply = _extract_team_content(out)
        agent_used = extract_agent_used(out)
        structured_output = None

        # If you have structured output extraction (echarts/json blocks), keep your working function here.
        # Example:
        # structured_output = extract_structured_output(reply) or None

    except Exception as e:
        # --- Fallback flow ---
        log_error(
            f"CHAT team_run_failed request_id={request_id} session_id={session_id} error={e}"
        )
        store.add(
            type="chat_error",
            session_id=session_id,
            payload={
                "request_id": request_id,
                "error": str(e),
                "table_name": selected_table,
                "user_query": user_query,
            },
        )

        fallback = _fallback_member(team)
        if fallback is not None:
            log_debug(
                f"CHAT fallback_start request_id={request_id} session_id={session_id} fallback_member=first_member"
            )
            try:
                reply = _call_member(fallback, final_prompt, session_id=session_id)
                agent_used = "fallback_member_0"
                structured_output = None
            except Exception as e2:
                log_error(
                    f"CHAT fallback_failed request_id={request_id} session_id={session_id} error={e2}"
                )
                reply = "System is temporarily unable to process your request. Please try again."
                agent_used = "none"
                structured_output = None
        else:
            reply = "System is temporarily unable to process your request. Please try again."
            agent_used = "none"
            structured_output = None

    dt_ms = int((time.perf_counter() - t0) * 1000)

    # Ensure reply never empty
    if not reply:
        reply = "No response generated. Please rephrase your question and try again."

    log_debug(
        f"CHAT request_done request_id={request_id} session_id={session_id} "
        f"agent_used={agent_used} latency_ms={dt_ms}"
    )

    store.add(
        type="chat_response",
        session_id=session_id,
        payload={
            "request_id": request_id,
            "agent_used": agent_used,
            "reply_preview": reply[:200],
            "table_name": selected_table,
            "latency_ms": dt_ms,
        },
    )

    return ChatResponse(
        session_id=session_id,
        agent_used=agent_used,
        reply=reply,
        structured_output=structured_output,
        raw={
            "request_id": request_id,
            "selected_table": selected_table,
        },
    )
