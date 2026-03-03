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

    # Some models prefix "json" line
    if raw.lower().startswith("json"):
        raw = raw[4:].strip()

    obj = json.loads(raw)

    if obj is None:
        raise ValueError("Dashboard agent returned JSON null (expected an object).")
    if not isinstance(obj, dict):
        raise ValueError(f"Dashboard agent returned JSON type {type(obj).__name__} (expected object).")

    return obj


def _normalize_echarts(obj: Any) -> Dict[str, Any]:
    """
    Your echarts tools return json.dumps(dict) => string.
    Normalize to dict for API contract.
    """
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, str):
        s = obj.strip()

        # Strip fenced blocks if present
        if s.startswith("```"):
            lines = s.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            s = "\n".join(lines).strip()

        # Some models prefix "echarts" / "json" labels
        if s.lower().startswith("echarts"):
            s = s[7:].strip()
        if s.lower().startswith("json"):
            s = s[4:].strip()

        try:
            loaded = json.loads(s)
            return loaded if isinstance(loaded, dict) else {"raw": loaded}
        except Exception:
            return {"raw": s}

    return {"raw": str(obj)}


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    request: Request,
    table_name: str = Query(..., min_length=1, description="Selected table e.g. public.orders"),
    session_id: Optional[str] = Query(default=None, description="Session id for stateful UX"),
    store: InMemoryEventStore = Depends(get_store),
    dashboard_agent: Agent = Depends(get_dashboard_agent),
) -> Dict[str, Any]:
    """
    Returns a default dashboard JSON (metrics + charts + tables) for a selected table.
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

    # Ask agent to return FINAL JSON only (no markdown)
    agent_input = (
        "[CONTEXT]\n"
        f"selected_table={table}\n"
        "[/CONTEXT]\n\n"
        "Generate a default business dashboard for selected_table.\n"
        "- First call describe_table(selected_table) to understand schema.\n"
        "- Use read-only aggregate queries via postgres tools to compute key metrics.\n"
        "- Use echarts tools to generate chart configs; set charts[].echarts to the tool output.\n"
        "- You may include 1-2 markdown tables via data-quality tools (tables[].markdown).\n"
        "- Focus on business-relevant columns; ignore ingestion/technical metadata columns.\n"
        "- Return ONLY valid JSON (no markdown fences, no extra commentary).\n\n"
        "Output JSON format:\n"
        "{\n"
        '  "table": "<schema.table>",\n'
        '  "metrics": [{"title": "...", "value": 123, "unit": null, "note": null}],\n'
        '  "charts": [{"title": "...", "echarts": "...", "note": null}],\n'
        '  "tables": [{"title": "...", "markdown": "...", "note": null}],\n'
        '  "column_descriptions": ["col: meaning ..."],\n'
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

        # Normalize + provide safe defaults
        metrics = payload.get("metrics") or []
        charts = payload.get("charts") or []
        tables = payload.get("tables") or []
        column_descriptions = payload.get("column_descriptions") or []
        notes = payload.get("notes") or []

        # Normalize echarts for each chart (string -> dict)
        normalized_charts = []
        for c in charts:
            if not isinstance(c, dict):
                continue
            c2 = dict(c)
            c2["title"] = str(c2.get("title") or "Chart")
            c2["echarts"] = _normalize_echarts(c2.get("echarts"))
            if "note" in c2 and c2["note"] is not None:
                c2["note"] = str(c2["note"])
            normalized_charts.append(c2)

        # Ensure tables are markdown strings
        normalized_tables = []
        for t in tables:
            if not isinstance(t, dict):
                continue
            t2 = dict(t)
            t2["title"] = str(t2.get("title") or "Table")
            t2["markdown"] = str(t2.get("markdown") or "")
            if "note" in t2 and t2["note"] is not None:
                t2["note"] = str(t2["note"])
            normalized_tables.append(t2)

        # Ensure metrics are structured
        normalized_metrics = []
        for m in metrics:
            if not isinstance(m, dict):
                continue
            m2 = dict(m)
            m2["title"] = str(m2.get("title") or "Metric")
            m2["value"] = m2.get("value", "")
            if "unit" in m2 and m2["unit"] is not None:
                m2["unit"] = str(m2["unit"])
            if "note" in m2 and m2["note"] is not None:
                m2["note"] = str(m2["note"])
            normalized_metrics.append(m2)

        resp: Dict[str, Any] = {
            "table": str(payload.get("table") or table),
            "session_id": sid,
            "metrics": normalized_metrics,
            "charts": normalized_charts,
            "tables": normalized_tables,
            "column_descriptions": [str(x) for x in column_descriptions if str(x).strip()],
            "notes": [str(x) for x in notes if str(x).strip()],
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
        payload={
            "request_id": request_id,
            "table_name": table,
            "metrics": len(resp["metrics"]),
            "charts": len(resp["charts"]),
            "tables": len(resp["tables"]),
        },
    )

    log_debug(
        f"DASHBOARD request_done request_id={request_id} session_id={sid} table={table} "
        f"metrics={len(resp['metrics'])} charts={len(resp['charts'])} tables={len(resp['tables'])}"
    )

    return resp
