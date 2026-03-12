from __future__ import annotations

from agno.agent import Agent
from agno.utils.log import log_debug

from src.config import get_llm_model


def create_dashboard_summary_agent() -> Agent:
    """
    Lightweight AI agent used only to generate short business notes
    from already-computed dashboard facts.
    """
    agent = Agent(
        id="dashboard_summary_agent",
        name="Dashboard Summary Agent",
        model=get_llm_model(),
        instructions=[
            "You are a business analytics narrator.",
            "Your input will contain dashboard facts already computed by the system.",
            "You must NOT generate SQL.",
            "You must NOT call tools.",
            "Write 2 to 4 short business notes only.",
            "Keep notes factual and concise.",
            "Do not add markdown fences.",
            "Return ONLY valid JSON in this format:",
            '{ "notes": ["note 1", "note 2"] }',
        ],
    )

    log_debug("Dashboard Summary Agent initialized")
    return agent

-------------------------------------------------------------------------------------------------------------
src/api/services/dashboard_builder.py

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from io import StringIO
from typing import Any, Dict, List, Optional

from agno.agent import Agent
from agno.utils.log import log_debug, log_error

from src.config.database import get_postgres_tools

# Adjust this import to your project if needed.
# It should return an object exposing:
# create_bar_chart(data, xlabel, ylabel, title)
# create_line_chart(data, xlabel, ylabel, title)
# create_pie_chart(data, xlabel, ylabel, title)
from src.tools.chart_tools import charttools


TECH_SUBSTRINGS = (
    "source",
    "file",
    "created",
    "updated",
    "ingest",
    "batch",
    "uuid",
    "hash",
    "flag",
    "metadata",
    "audit",
)

NUMERIC_TYPES = {
    "integer",
    "bigint",
    "smallint",
    "numeric",
    "real",
    "double precision",
    "decimal",
}

TIME_TYPES = {
    "date",
    "timestamp without time zone",
    "timestamp with time zone",
    "timestamp",
}

PREFERRED_NUMERIC_NAMES = (
    "amount",
    "revenue",
    "sales",
    "price",
    "cost",
    "profit",
    "quantity",
    "qty",
    "total",
    "value",
)

PREFERRED_CATEGORY_NAMES = (
    "status",
    "category",
    "type",
    "region",
    "segment",
    "product",
    "customer",
    "country",
    "city",
)

PREFERRED_TIME_NAMES = (
    "date",
    "time",
    "month",
    "year",
    "order_date",
    "transaction_date",
    "created_date",
)


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    is_nullable: str


def _quote_ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"Invalid identifier: {name}")
    return f'"{name}"'


def _quote_table(table_name: str) -> str:
    parts = table_name.split(".")
    if len(parts) == 1:
        return _quote_ident(parts[0])
    if len(parts) == 2:
        return f"{_quote_ident(parts[0])}.{_quote_ident(parts[1])}"
    raise ValueError(f"Invalid table name: {table_name}")


def _parse_csv_rows(text: str) -> List[Dict[str, str]]:
    raw = (text or "").strip()
    if not raw:
        return []
    lowered = raw.lower()
    if lowered.startswith("error executing query:") or lowered.startswith("an unexpected error occurred:"):
        return []

    reader = csv.DictReader(StringIO(raw))
    return [dict(row) for row in reader]


def _extract_content(out: Any) -> str:
    if out is None:
        return ""

    candidates: List[str] = []

    def collect(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            s = value.strip()
            if s:
                candidates.append(s)
            return
        if isinstance(value, dict):
            try:
                candidates.append(json.dumps(value, ensure_ascii=False))
            except Exception:
                candidates.append(str(value))
            return
        s = str(value).strip()
        if s:
            candidates.append(s)

    if hasattr(out, "content"):
        collect(getattr(out, "content", None))

    if hasattr(out, "messages"):
        msgs = getattr(out, "messages", None)
        if isinstance(msgs, list):
            for msg in msgs:
                if isinstance(msg, dict):
                    collect(msg.get("content"))
                elif hasattr(msg, "content"):
                    collect(getattr(msg, "content", None))
                else:
                    collect(msg)

    if not candidates:
        return ""

    for candidate in reversed(candidates):
        if '"notes"' in candidate:
            return candidate
    return candidates[-1]


def _safe_json_object(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty JSON text")

    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    if raw.lower().startswith("json"):
        raw = raw[4:].strip()

    try:
        payload = json.loads(raw)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise
        payload = json.loads(match.group(0))

    if not isinstance(payload, dict):
        raise ValueError("Expected JSON object")
    return payload


def _is_technical(col: ColumnInfo) -> bool:
    name = col.name.lower()
    return any(token in name for token in TECH_SUBSTRINGS)


def _score_name(name: str, preferred: tuple[str, ...]) -> int:
    lowered = name.lower()
    for idx, token in enumerate(preferred):
        if token in lowered:
            return idx
    return 999


def _parse_schema(pg: Any, table_name: str) -> List[ColumnInfo]:
    bare_table = table_name.split(".")[-1]
    rows = _parse_csv_rows(pg.describe_table(bare_table))
    cols: List[ColumnInfo] = []
    for row in rows:
        cols.append(
            ColumnInfo(
                name=str(row.get("column_name") or "").strip(),
                data_type=str(row.get("data_type") or "").strip().lower(),
                is_nullable=str(row.get("is_nullable") or "").strip(),
            )
        )
    return cols


def _pick_numeric_columns(columns: List[ColumnInfo]) -> List[ColumnInfo]:
    numeric = [c for c in columns if c.data_type in NUMERIC_TYPES and not _is_technical(c)]
    return sorted(numeric, key=lambda c: _score_name(c.name, PREFERRED_NUMERIC_NAMES))


def _pick_time_columns(columns: List[ColumnInfo]) -> List[ColumnInfo]:
    time_cols = [c for c in columns if c.data_type in TIME_TYPES and not _is_technical(c)]
    return sorted(time_cols, key=lambda c: _score_name(c.name, PREFERRED_TIME_NAMES))


def _pick_category_columns(columns: List[ColumnInfo]) -> List[ColumnInfo]:
    categories: List[ColumnInfo] = []
    for c in columns:
        dtype = c.data_type
        if _is_technical(c):
            continue
        if dtype in NUMERIC_TYPES or dtype in TIME_TYPES:
            continue
        categories.append(c)
    return sorted(categories, key=lambda c: _score_name(c.name, PREFERRED_CATEGORY_NAMES))


def _run_scalar(pg: Any, query: str) -> str:
    rows = _parse_csv_rows(pg.run_query(query))
    if not rows:
        return ""
    first_row = rows[0]
    if not first_row:
        return ""
    return str(next(iter(first_row.values())))


def _run_rows(pg: Any, query: str) -> List[Dict[str, str]]:
    return _parse_csv_rows(pg.run_query(query))


def _to_number(value: Any) -> int | float | str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        if "." in text:
            return round(float(text), 2)
        return int(text)
    except Exception:
        return text


def _metric_total_records(pg: Any, qtable: str) -> Dict[str, Any]:
    value = _to_number(_run_scalar(pg, f"SELECT COUNT(*) AS total_records FROM {qtable}"))
    return {"title": "Total Records", "value": value, "unit": None, "note": None}


def _metric_sum_avg(pg: Any, qtable: str, col: ColumnInfo) -> List[Dict[str, Any]]:
    qcol = _quote_ident(col.name)
    rows = _run_rows(
        pg,
        f"SELECT COALESCE(SUM({qcol}), 0) AS total_value, COALESCE(AVG({qcol}), 0) AS avg_value "
        f"FROM {qtable}",
    )
    if not rows:
        return []
    row = rows[0]
    return [
        {
            "title": f"Total {col.name}",
            "value": _to_number(row.get("total_value")),
            "unit": None,
            "note": None,
        },
        {
            "title": f"Average {col.name}",
            "value": _to_number(row.get("avg_value")),
            "unit": None,
            "note": None,
        },
    ]


def _metric_distinct(pg: Any, qtable: str, col: ColumnInfo) -> Dict[str, Any]:
    qcol = _quote_ident(col.name)
    value = _to_number(
        _run_scalar(
            pg,
            f"SELECT COUNT(DISTINCT {qcol}) AS distinct_count FROM {qtable} WHERE {qcol} IS NOT NULL",
        )
    )
    return {
        "title": f"Distinct {col.name}",
        "value": value,
        "unit": None,
        "note": None,
    }


def _make_bar_chart(chart_tool: Any, title: str, xlabel: str, ylabel: str, rows: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    if not rows:
        return None
    data: Dict[str, Any] = {}
    keys = list(rows[0].keys())
    if len(keys) < 2:
        return None
    x_key, y_key = keys[0], keys[1]
    for row in rows:
        label = str(row.get(x_key) or "").strip()
        if not label:
            continue
        data[label] = _to_number(row.get(y_key))
    if not data:
        return None
    return {
        "title": title,
        "echarts": chart_tool.create_bar_chart(data=data, xlabel=xlabel, ylabel=ylabel, title=title),
        "note": None,
    }


def _make_pie_chart(chart_tool: Any, title: str, xlabel: str, ylabel: str, rows: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    if not rows:
        return None
    data: Dict[str, Any] = {}
    keys = list(rows[0].keys())
    if len(keys) < 2:
        return None
    x_key, y_key = keys[0], keys[1]
    for row in rows:
        label = str(row.get(x_key) or "").strip()
        if not label:
            continue
        data[label] = _to_number(row.get(y_key))
    if not data:
        return None
    return {
        "title": title,
        "echarts": chart_tool.create_pie_chart(data=data, xlabel=xlabel, ylabel=ylabel, title=title),
        "note": None,
    }


def _make_line_chart(chart_tool: Any, title: str, xlabel: str, ylabel: str, rows: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    if not rows:
        return None
    data: Dict[str, Any] = {}
    keys = list(rows[0].keys())
    if len(keys) < 2:
        return None
    x_key, y_key = keys[0], keys[1]
    for row in rows:
        label = str(row.get(x_key) or "").strip()
        if not label:
            continue
        data[label] = _to_number(row.get(y_key))
    if not data:
        return None
    return {
        "title": title,
        "echarts": chart_tool.create_line_chart(data=data, xlabel=xlabel, ylabel=ylabel, title=title),
        "note": None,
    }


def _top_category_rows(pg: Any, qtable: str, col: ColumnInfo) -> List[Dict[str, str]]:
    qcol = _quote_ident(col.name)
    query = (
        f"SELECT {qcol} AS category, COUNT(*) AS record_count "
        f"FROM {qtable} WHERE {qcol} IS NOT NULL "
        f"GROUP BY {qcol} ORDER BY record_count DESC LIMIT 10"
    )
    return _run_rows(pg, query)


def _trend_rows(pg: Any, qtable: str, time_col: ColumnInfo, num_col: Optional[ColumnInfo]) -> List[Dict[str, str]]:
    qtime = _quote_ident(time_col.name)
    if num_col is not None:
        qnum = _quote_ident(num_col.name)
        metric_expr = f"COALESCE(SUM({qnum}), 0)"
        metric_name = "metric_value"
    else:
        metric_expr = "COUNT(*)"
        metric_name = "record_count"

    query = (
        f"SELECT DATE_TRUNC('month', {qtime})::date AS period, {metric_expr} AS {metric_name} "
        f"FROM {qtable} "
        f"WHERE {qtime} IS NOT NULL "
        f"GROUP BY period ORDER BY period LIMIT 24"
    )
    return _run_rows(pg, query)


def _category_metric_rows(pg: Any, qtable: str, cat_col: ColumnInfo, num_col: ColumnInfo) -> List[Dict[str, str]]:
    qcat = _quote_ident(cat_col.name)
    qnum = _quote_ident(num_col.name)
    query = (
        f"SELECT {qcat} AS category, COALESCE(SUM({qnum}), 0) AS metric_total "
        f"FROM {qtable} "
        f"WHERE {qcat} IS NOT NULL "
        f"GROUP BY {qcat} ORDER BY metric_total DESC LIMIT 10"
    )
    return _run_rows(pg, query)


def _markdown_from_rows(title: str, rows: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    if not rows:
        return None

    headers = list(rows[0].keys())
    md = []
    md.append("| " + " | ".join(headers) + " |")
    md.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        md.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")

    return {"title": title, "markdown": "\n".join(md), "note": None}


def _missing_values_table(pg: Any, qtable: str, cols: List[ColumnInfo]) -> Optional[Dict[str, Any]]:
    rows_out: List[Dict[str, str]] = []
    for col in cols[:5]:
        qcol = _quote_ident(col.name)
        rows = _run_rows(
            pg,
            f"SELECT COUNT(*) AS total_rows, COUNT(*) - COUNT({qcol}) AS missing_count "
            f"FROM {qtable}",
        )
        if not rows:
            continue
        total = int(str(rows[0].get("total_rows") or "0"))
        missing = int(str(rows[0].get("missing_count") or "0"))
        pct = round((missing / total) * 100, 2) if total else 0.0
        rows_out.append(
            {
                "column_name": col.name,
                "missing_count": str(missing),
                "missing_pct": str(pct),
            }
        )

    return _markdown_from_rows("Missing Values Summary", rows_out)


def _build_column_descriptions(
    numeric_cols: List[ColumnInfo],
    category_cols: List[ColumnInfo],
    time_cols: List[ColumnInfo],
) -> List[str]:
    desc: List[str] = []
    if numeric_cols:
        for col in numeric_cols[:2]:
            desc.append(f"{col.name}: key numeric measure useful for totals, averages, and contribution analysis.")
    if category_cols:
        for col in category_cols[:2]:
            desc.append(f"{col.name}: business dimension useful for segmentation and top-N analysis.")
    if time_cols:
        for col in time_cols[:1]:
            desc.append(f"{col.name}: time dimension useful for trend and seasonality analysis.")
    return desc


def _deterministic_notes(metrics: List[Dict[str, Any]], charts: List[Dict[str, Any]], tables: List[Dict[str, Any]]) -> List[str]:
    notes: List[str] = []
    if metrics:
        notes.append(f"{len(metrics)} key metrics were generated from the selected table.")
    if charts:
        notes.append(f"{len(charts)} business charts were generated to summarize trends and distributions.")
    if tables:
        notes.append(f"{len(tables)} supporting summary tables were included for quick inspection.")
    return notes[:4]


def _ai_notes(summary_agent: Optional[Agent], payload: Dict[str, Any]) -> List[str]:
    if summary_agent is None:
        return _deterministic_notes(payload["metrics"], payload["charts"], payload["tables"])

    prompt = (
        "Generate dashboard notes from these facts.\n"
        "Return only JSON.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        out = summary_agent.run(input=prompt)
        text = _extract_content(out)
        obj = _safe_json_object(text)
        notes = obj.get("notes")
        if isinstance(notes, list):
            cleaned = [str(x) for x in notes if str(x).strip()]
            if cleaned:
                return cleaned[:4]
    except Exception as e:
        log_error(f"Dashboard summary agent failed: {e}")

    return _deterministic_notes(payload["metrics"], payload["charts"], payload["tables"])


def build_dashboard(
    table_name: str,
    session_id: str,
    request_id: str,
    summary_agent: Optional[Agent] = None,
) -> Dict[str, Any]:
    pg = get_postgres_tools()
    chart_tool = charttools()

    qtable = _quote_table(table_name)
    columns = _parse_schema(pg, table_name)
    if not columns:
        raise ValueError("Could not read table schema")

    numeric_cols = _pick_numeric_columns(columns)
    time_cols = _pick_time_columns(columns)
    category_cols = _pick_category_columns(columns)

    metrics: List[Dict[str, Any]] = [_metric_total_records(pg, qtable)]

    if numeric_cols:
        metrics.extend(_metric_sum_avg(pg, qtable, numeric_cols[0]))
    if category_cols:
        metrics.append(_metric_distinct(pg, qtable, category_cols[0]))

    metrics = metrics[:5]

    charts: List[Dict[str, Any]] = []

    if category_cols:
        top_rows = _top_category_rows(pg, qtable, category_cols[0])
        chart = _make_bar_chart(
            chart_tool,
            title=f"Top {category_cols[0].name} by record count",
            xlabel=category_cols[0].name,
            ylabel="Count",
            rows=top_rows,
        )
        if chart:
            charts.append(chart)

        pie = _make_pie_chart(
            chart_tool,
            title=f"{category_cols[0].name} share",
            xlabel=category_cols[0].name,
            ylabel="Count",
            rows=top_rows[:6],
        )
        if pie:
            charts.append(pie)

    if time_cols:
        trend = _trend_rows(pg, qtable, time_cols[0], numeric_cols[0] if numeric_cols else None)
        chart = _make_line_chart(
            chart_tool,
            title=f"Trend by {time_cols[0].name}",
            xlabel=time_cols[0].name,
            ylabel=numeric_cols[0].name if numeric_cols else "Count",
            rows=trend,
        )
        if chart:
            charts.append(chart)

    if numeric_cols and category_cols:
        combo = _category_metric_rows(pg, qtable, category_cols[0], numeric_cols[0])
        chart = _make_bar_chart(
            chart_tool,
            title=f"{numeric_cols[0].name} by {category_cols[0].name}",
            xlabel=category_cols[0].name,
            ylabel=numeric_cols[0].name,
            rows=combo,
        )
        if chart:
            charts.append(chart)

    charts = charts[:4]

    tables: List[Dict[str, Any]] = []
    if category_cols:
        top_rows = _top_category_rows(pg, qtable, category_cols[0])
        top_table = _markdown_from_rows(f"Top {category_cols[0].name} Summary", top_rows)
        if top_table:
            tables.append(top_table)

    important_cols = []
    if numeric_cols:
        important_cols.extend(numeric_cols[:2])
    if category_cols:
        important_cols.extend(category_cols[:2])
    if time_cols:
        important_cols.extend(time_cols[:1])

    missing_table = _missing_values_table(pg, qtable, important_cols)
    if missing_table:
        tables.append(missing_table)

    tables = tables[:2]

    column_descriptions = _build_column_descriptions(numeric_cols, category_cols, time_cols)

    payload = {
        "table": table_name,
        "session_id": session_id,
        "metrics": metrics,
        "charts": charts,
        "tables": tables,
        "column_descriptions": column_descriptions,
        "notes": [],
        "raw": {
            "request_id": request_id,
            "numeric_columns": [c.name for c in numeric_cols],
            "category_columns": [c.name for c in category_cols],
            "time_columns": [c.name for c in time_cols],
        },
    }

    payload["notes"] = _ai_notes(summary_agent, payload)

    log_debug(
        f"DASHBOARD builder_done table={table_name} metrics={len(payload['metrics'])} "
        f"charts={len(payload['charts'])} tables={len(payload['tables'])}"
    )

    return payload




-------------------------------------------------
 src/api/models.py
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
    unit: Optional[str] = 
    None
    note: Optional[str] = None


class DashboardResponse(BaseModel):
    table: str
    session_id: Optional[str] = None
    metrics: List[DashboardMetric] = Field(default_factory=list)
    charts: List[DashboardChart] = Field(default_factory=list)
    tables: List[DashboardTable] = Field(default_factory=list)
    column_descriptions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)

--------------------------
src/api/deps.py


from __future__ import annotations

from typing import Optional

from agno.agent import Agent
from agno.team import Team

from src.api.store import InMemoryEventStore

_store: Optional[InMemoryEventStore] = None
_team: Optional[Team] = None
_insights_agent: Optional[Agent] = None
_dashboard_summary_agent: Optional[Agent] = None


def init_api_dependencies(
    *,
    store: InMemoryEventStore,
    team: Team,
    insights_agent: Agent | None = None,
    dashboard_summary_agent: Agent | None = None,
) -> None:
    global _store, _team, _insights_agent, _dashboard_summary_agent
    _store = store
    _team = team

    if insights_agent is not None:
        _insights_agent = insights_agent

    if dashboard_summary_agent is not None:
        _dashboard_summary_agent = dashboard_summary_agent



def get_store() -> InMemoryEventStore:
    if _store is None:
        raise RuntimeError("Store dependency not initialized")
    return _store


def get_team() -> Team:
    if _team is None:
        raise RuntimeError("Team dependency not initialized")
    return _team


def get_insights_agent() -> Agent:
    if _insights_agent is None:
        raise RuntimeError("Insights agent dependency not initialized")
    return _insights_agent


def get_dashboard_summary_agent() -> Agent:
    if _dashboard_summary_agent is None:
        raise RuntimeError("Dashboard summary agent dependency not initialized")
    return _dashboard_summary_agent

----------------------------------------

src/api/routes/dashboard.py

from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from agno.agent import Agent
from agno.utils.log import log_debug, log_error

from src.api.auth.rate_limiter import rate_limit
from src.api.auth.security import get_current_user
from src.api.deps import get_dashboard_summary_agent, get_store
from src.api.models import DashboardResponse
from src.api.services.dashboard_builder import build_dashboard
from src.api.store import InMemoryEventStore

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    request: Request,
    table_name: str = Query(..., min_length=1, description="Selected table e.g. public.orders"),
    session_id: Optional[str] = Query(default=None, description="Session id for stateful UX"),
    store: InMemoryEventStore = Depends(get_store),
    dashboard_summary_agent: Agent = Depends(get_dashboard_summary_agent),
    user=Depends(get_current_user),
) -> Dict[str, object]:
    request_id = getattr(request.state, "request_id", "unknown")
    sid = session_id or "default"
    table = table_name.strip()

    rate_limit(user["user_id"])
    store.set_session_value(sid, "selected_table", table)

    log_debug(
        f"DASHBOARD request_start request_id={request_id} "
        f"session_id={sid} table={table} user_id={user['user_id']}"
    )

    store.add(
        type="dashboard_request",
        session_id=sid,
        payload={
            "request_id": request_id,
            "table_name": table,
            "user_id": user["user_id"],
        },
    )

    try:
        response = build_dashboard(
            table_name=table,
            session_id=sid,
            request_id=request_id,
            summary_agent=dashboard_summary_agent,
        )
    except Exception as e:
        log_error(
            f"DASHBOARD request_failed request_id={request_id} "
            f"session_id={sid} table={table} error={e}"
        )
        store.add(
            type="dashboard_error",
            session_id=sid,
            payload={
                "request_id": request_id,
                "table_name": table,
                "user_id": user["user_id"],
                "error": str(e),
            },
        )
        raise HTTPException(status_code=500, detail=f"Failed to generate dashboard: {e}")

    store.add(
        type="dashboard_response",
        session_id=sid,
        payload={
            "request_id": request_id,
            "table_name": table,
            "user_id": user["user_id"],
            "metrics": len(response["metrics"]),
            "charts": len(response["charts"]),
            "tables": len(response["tables"]),
        },
    )

    log_debug(
        f"DASHBOARD request_done request_id={request_id} session_id={sid} "
        f"table={table} metrics={len(response['metrics'])} "
        f"charts={len(response['charts'])} tables={len(response['tables'])}"
    )

    return response
    --------------------------------



from __future__ import annotations

from fastapi import FastAPI
from agno.os import AgentOS

from src.agents.dashboard_summary_agent import create_dashboard_summary_agent
from src.agents.insights_agent import create_insights_agent
from src.api.app_factory import create_app
from src.api.orchestrator_team import build_default_team
from src.api.store import InMemoryEventStore

# Existing agents
from src.agents import Agent1, Agent2, Agent3  # adjust imports to your repo


agent_1 = Agent1()
agent_2 = Agent2()
agent_3 = Agent3()

agent_os = AgentOS(
    description="Agno AgentOS Backend",
    agents=[agent_1, agent_2, agent_3],
)

base_app = agent_os.get_app()

store = InMemoryEventStore(max_events=5000)
team = build_default_team()
insights_agent = create_insights_agent()
dashboard_summary_agent = create_dashboard_summary_agent()

app: FastAPI = create_app(
    base_app=base_app,
    store=store,
    team=team,
    insights_agent=insights_agent,
    dashboard_summary_agent=dashboard_summary_agent,
)

if __name__ == "__main__":
    agent_os.serve(app="main:app", host="0.0.0.0", port=9999, reload=True)
