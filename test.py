# src/api/routes/insights.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from agno.agent import Agent
from agno.utils.log import log_debug, log_error

from src.api.deps import get_store, get_insights_agent
from src.api.store import InMemoryEventStore

router = APIRouter(prefix="/api/insights", tags=["insights"])


def _extract_content(out: Any) -> str:
    if out is None:
        return ""
    if hasattr(out, "content"):
        c = getattr(out, "content")
        return "" if c is None else str(c)
    return str(out)


def _safe_json_loads(s: str) -> Dict[str, Any]:
    """
    Insights agent should return pure JSON.
    If it ever returns fences, we try best-effort stripping.
    """
    raw = (s or "").strip()

    # Best-effort strip markdown fences if present (defensive)
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        # Sometimes LLM writes ```json\n{...}
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()

    return json.loads(raw)


@router.get("/prompts")
def get_insight_prompts(
    request: Request,
    table_name: str = Query(..., min_length=1, description="Selected table e.g. public.orders"),
    session_id: Optional[str] = Query(default=None, description="Session id for stateful UX"),
    store: InMemoryEventStore = Depends(get_store),
    insights_agent: Agent = Depends(get_insights_agent),
) -> Dict[str, Any]:
    request_id = getattr(request.state, "request_id", "unknown")
    sid = session_id or "default"

    table_name = table_name.strip()

    # Bind table to session (same pattern as chat)
    store.set_session_value(sid, "selected_table", table_name)

    prompt_count = int(os.getenv("INSIGHTS_PROMPT_COUNT", 12))

    agent_input = (
        "[CONTEXT]\n"
        f"selected_table={table_name}\n"
        f"prompt_count={prompt_count}\n"
        "[/CONTEXT]\n\n"
        "Generate prompts for the selected_table. "
        "You MUST call describe_table(selected_table) before generating prompts. "
        f"Return exactly {prompt_count} prompts in strict JSON."
    )

    log_debug(
        f"INSIGHTS prompts_request request_id={request_id} session_id={sid} table={table_name} count={prompt_count}"
    )

    store.add(
        type="insights_prompts_request",
        session_id=sid,
        payload={"request_id": request_id, "table_name": table_name, "count": prompt_count},
    )

    try:
        out = insights_agent.run(input=agent_input, session_id=sid)
        text = _extract_content(out)
        payload = _safe_json_loads(text)

        # Basic shape check
        if "prompts" not in payload or not isinstance(payload["prompts"], list):
            raise ValueError("Insights agent returned invalid JSON format (missing prompts list)")

        # Ensure prompts count is controlled
        prompts: List[str] = [str(x).strip() for x in payload["prompts"] if str(x).strip()]
        prompts = prompts[:prompt_count]

        resp = {"table": table_name, "prompts": prompts}

    except Exception as e:
        log_error(
            f"INSIGHTS prompts_failed request_id={request_id} session_id={sid} table={table_name} error={e}"
        )
        store.add(
            type="insights_prompts_error",
            session_id=sid,
            payload={"request_id": request_id, "table_name": table_name, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Failed to generate insight prompts")

    store.add(
        type="insights_prompts_response",
        session_id=sid,
        payload={"request_id": request_id, "table_name": table_name, "count": len(resp["prompts"])},
    )

    log_debug(
        f"INSIGHTS prompts_done request_id={request_id} session_id={sid} table={table_name} returned={len(resp['prompts'])}"
    )

    return resp
