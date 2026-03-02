# src/api/routes/dashboard.py
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from agno.agent import Agent
from agno.utils.log import log_debug, log_error

from src.api.deps import get_dashboard_agent, get_store
from src.api.models import DashboardResponse
from src.api.store import InMemoryEventStore

router = APIRouter(prefix="/api", tags=["dashboard"])


def _extract_content(out: Any) -> str:
    if out is None:
        return ""
    if hasattr(out, "content"):
        c = getattr(out, "content")
        return "" if c is None else str(c)
    return str(out)


def _safe_json_loads(s: str) -> Dict[str, Any]:
    """
    Dashboard agent must return pure JSON.
    Defensive stripping if markdown fences slip through.
    """
    raw = (s or "").strip()

    # Strip fenced blocks like ```json ... ```
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    if raw.lower().startswith("json"):
        raw = raw[4:].strip()

    obj = json.loads(raw)

    if obj is None:
        raise ValueError("Dashboard agent returned JSON null (expected an object).")
    if not isinstance(obj, dict):
        raise ValueError(f"Dashboard agent returned JSON type {type(obj).__name__} (expected object).")

    return obj


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    request: Request,
    table_name: str = Query(..., min_length=1, description="Selected table e.g. public.orders"),
    session_id: Optional[str] = Query(default=None, description="Session id for stateful UX"),
    store: InMemoryEventStore = Depends(get_store),
    dashboard_agent: Agent = Depends(get_dashboard_agent),
) -> Dict[str, Any]:
    """
    Returns a default dashboard JSON (KPIs + ECharts configs) for a selected table.
    UI calls this when Dashboard tab is opened.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    sid = session_id or "default"
    table = table_name.strip()

    # Bind table to session (consistent with chat/insights)
    store.set_session_value(sid, "selected_table", table)

    log_debug(f"DASHBOARD request_start request_id={request_id} session_id={sid} table={table}")

    store.add(
        type="dashboard_request",
        session_id=sid,
        payload={"request_id": request_id, "table_name": table},
    )

    # Prompt sent to dashboard agent (Agno-native)
    agent_input = (
        "[CONTEXT]\n"
        f"selected_table={table}\n"
        "[/CONTEXT]\n\n"
        "Generate a default business dashboard for selected_table.\n"
        "- First call describe_table(selected_table) to understand schema.\n"
        "- If helpful, you may run read-only aggregate queries via postgres tools.\n"
        "- Focus on business-relevant columns; ignore ingestion/technical metadata columns.\n"
        "- Return ONLY valid JSON (no markdown).\n"
        "Output JSON format:\n"
        "{\n"
        '  "table": "<schema.table>",\n'
        '  "kpis": [{"title": "...", "value": 123, "unit": "%", "note": "..."}],\n'
        '  "charts": [{"title": "...", "echarts": {...}, "note": "..."}],\n'
        '  "notes": ["..."]\n'
        "}\n"
    )

    try:
        out = dashboard_agent.run(input=agent_input, session_id=sid)
        text = _extract_content(out)

        log_debug(
            f"DASHBOARD agent_raw_preview request_id={request_id} session_id={sid} "
            f"preview='{(text or '')[:400]}'"
        )

        payload = _safe_json_loads(text)

        # Minimal shape validation (keep light)
        if "table" not in payload:
            payload["table"] = table
        if "kpis" not in payload:
            payload["kpis"] = []
        if "charts" not in payload:
            payload["charts"] = []
        if "notes" not in payload:
            payload["notes"] = []

        resp: Dict[str, Any] = {
            "table": str(payload.get("table") or table),
            "session_id": sid,
            "kpis": payload.get("kpis") or [],
            "charts": payload.get("charts") or [],
            "notes": payload.get("notes") or [],
            "raw": {"request_id": request_id},
        }

    except Exception as e:
        log_error(
            f"DASHBOARD request_failed request_id={request_id} session_id={sid} table={table} error={e}"
        )
        store.add(
            type="dashboard_error",
            session_id=sid,
            payload={"request_id": request_id, "table_name": table, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Failed to generate dashboard")

    store.add(
        type="dashboard_response",
        session_id=sid,
        payload={"request_id": request_id, "table_name": table, "kpis": len(resp["kpis"]), "charts": len(resp["charts"])},
    )

    log_debug(
        f"DASHBOARD request_done request_id={request_id} session_id={sid} table={table} "
        f"kpis={len(resp['kpis'])} charts={len(resp['charts'])}"
    )

    # Return dict so FastAPI can validate against response_model cleanly
    return resp
