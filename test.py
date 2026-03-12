instructions = [
    "You are a Business Dashboard Generator Agent.",
    "Your task is to generate a default dashboard for the selected_table.",
    "You MUST call describe_table(selected_table) first.",
    "Use only business-relevant columns for analysis.",
    "Ignore metadata, ingestion, technical, audit, or system-generated columns such as source_file, record_created, updated_at, created_at, batch_id, uuid, hash, file_name.",
    "Use postgres tools to compute real values for metrics.",
    "Use chart tools to generate chart JSON when needed.",
    "Use data quality tools only if they add useful business value.",
    "Generate a compact business dashboard with:",
    "- 3 to 5 key metrics",
    "- 2 to 4 charts",
    "- 0 to 2 markdown tables",
    "- 2 to 5 short business notes",
    "Charts should be meaningful for business users such as top categories, trend over time, or distribution of important measures.",
    "Metrics should focus on record volume, totals, averages, distinct categories, or business-critical values.",
    "Do NOT generate unnecessary prompts or technical analysis.",
    "Do NOT explain your reasoning.",
    "Do NOT wrap output in markdown fences.",
    "Return ONLY valid JSON.",
    "Return JSON in exactly this format:",
    "{",
    '  "table": "<schema.table>",',
    '  "metrics": [{"title": "...", "value": 123, "unit": null, "note": "..."}],',
    '  "charts": [{"title": "...", "echarts": "...", "note": "..."}],',
    '  "tables": [{"title": "...", "markdown": "...", "note": "..."}],',
    '  "notes": ["..."]',
    "}",
    "For each chart, set charts[].echarts to the raw output returned by the chart tool.",
],


-------------------------------------------------------------------------------------------------------------

# src/api/routes/dashboard.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

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
        c = getattr(out, "content", None)
        if c is not None and str(c).strip():
            return str(c)

    if hasattr(out, "messages"):
        msgs = getattr(out, "messages", None)
        if isinstance(msgs, list):
            for msg in reversed(msgs):
                if isinstance(msg, dict):
                    c = msg.get("content")
                    if c is not None and str(c).strip():
                        return str(c)
                elif hasattr(msg, "content"):
                    c = getattr(msg, "content", None)
                    if c is not None and str(c).strip():
                        return str(c)

    return ""


def _strip_fences(raw: str) -> str:
    text = (raw or "").strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if text.lower().startswith("json"):
        text = text[4:].strip()

    return text


def _load_payload(text: str) -> Dict[str, Any]:
    cleaned = _strip_fences(text)
    if not cleaned:
        raise ValueError("Dashboard agent returned empty content")

    payload = json.loads(cleaned)
    if payload is None or not isinstance(payload, dict):
        raise ValueError("Dashboard agent did not return a valid JSON object")

    return payload


def _normalize_echarts(value: Any) -> Dict[str, Any] | str:
    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        raw = _strip_fences(value)

        if raw.lower().startswith("echarts"):
            raw = raw[7:].strip()

        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else raw
        except Exception:
            return raw

    return str(value)


def _normalize_metrics(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        normalized.append(
            {
                "title": str(item.get("title") or "Metric"),
                "value": item.get("value", ""),
                "unit": None if item.get("unit") is None else str(item.get("unit")),
                "note": None if item.get("note") is None else str(item.get("note")),
            }
        )
    return normalized


def _normalize_charts(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        raw_chart = item.get("echarts", item.get("echart"))
        normalized.append(
            {
                "title": str(item.get("title") or "Chart"),
                "echarts": _normalize_echarts(raw_chart),
                "note": None if item.get("note") is None else str(item.get("note")),
            }
        )
    return normalized


def _normalize_tables(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        normalized.append(
            {
                "title": str(item.get("title") or "Table"),
                "markdown": str(item.get("markdown") or ""),
                "note": None if item.get("note") is None else str(item.get("note")),
            }
        )
    return normalized


def _normalize_notes(items: Any) -> List[str]:
    if not isinstance(items, list):
        return []
    return [str(x) for x in items if str(x).strip()]


def _build_agent_input(table: str) -> str:
    return (
        "[CONTEXT]\n"
        f"selected_table={table}\n"
        "[/CONTEXT]\n\n"
        "Generate a default business dashboard for selected_table.\n"
        "You must return ONLY valid JSON in the agreed schema."
    )


def _build_response(
    table: str,
    sid: str,
    request_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "table": str(payload.get("table") or table),
        "session_id": sid,
        "metrics": _normalize_metrics(payload.get("metrics")),
        "charts": _normalize_charts(payload.get("charts")),
        "tables": _normalize_tables(payload.get("tables")),
        "notes": _normalize_notes(payload.get("notes")),
        "raw": {"request_id": request_id},
    }


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    request: Request,
    table_name: str = Query(..., min_length=1, description="Selected table e.g. public.orders"),
    session_id: Optional[str] = Query(default=None, description="Session id for stateful UX"),
    store: InMemoryEventStore = Depends(get_store),
    dashboard_agent: Agent = Depends(get_dashboard_agent),
) -> Dict[str, Any]:
    request_id = getattr(request.state, "request_id", "unknown")
    sid = session_id or "default"
    table = table_name.strip()

    store.set_session_value(sid, "selected_table", table)

    log_debug(f"DASHBOARD request_start request_id={request_id} session_id={sid} table={table}")
    store.add(
        type="dashboard_request",
        session_id=sid,
        payload={"request_id": request_id, "table_name": table},
    )

    try:
        out = dashboard_agent.run(input=_build_agent_input(table), session_id=sid)
        text = _extract_content(out)

        log_debug(
            f"DASHBOARD agent_raw_preview request_id={request_id} "
            f"session_id={sid} preview='{(text or '')[:400]}'"
        )

        payload = _load_payload(text)
        response = _build_response(table, sid, request_id, payload)

    except Exception as e:
        log_error(
            f"DASHBOARD request_failed request_id={request_id} "
            f"session_id={sid} table={table} error={e}"
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
            "metrics": len(response["metrics"]),
            "charts": len(response["charts"]),
            "tables": len(response["tables"]),
        },
    )

    log_debug(
        f"DASHBOARD request_done request_id={request_id} session_id={sid} table={table} "
        f"metrics={len(response['metrics'])} charts={len(response['charts'])} "
        f"tables={len(response['tables'])}"
    )

    return response


-----------------------------------------------

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DashboardChart(BaseModel):
    title: str
    echarts: Dict[str, Any] | str
    note: Optional[str] = None


class DashboardTable(BaseModel):
    title: str
    markdown: str
    note: Optional[str] = None


class DashboardMetric(BaseModel):
    title: str
    value: int | float | str
    unit: Optional[str] = None
    note: Optional[str] = None


class DashboardResponse(BaseModel):
    table: str
    session_id: Optional[str] = None
    metrics: List[DashboardMetric] = Field(default_factory=list)
    charts: List[DashboardChart] = Field(default_factory=list)
    tables: List[DashboardTable] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)
