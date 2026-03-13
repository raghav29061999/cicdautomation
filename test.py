from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any, Dict, List, Optional

from agno.agent import Agent
from agno.utils.log import log_debug, log_error

from src.config.database import get_postgres_tools
from src.tools import ChartTools


# -----------------------------------------------------------
# Utilities
# -----------------------------------------------------------


def _parse_csv_rows(text: str) -> List[Dict[str, str]]:
    raw = (text or "").strip()
    if not raw:
        return []

    lowered = raw.lower()
    if lowered.startswith("error executing query"):
        return []

    reader = csv.DictReader(StringIO(raw))
    return [dict(row) for row in reader]


def _extract_content(out: Any) -> str:
    if out is None:
        return ""

    if hasattr(out, "content"):
        content = getattr(out, "content")
        if content:
            return str(content)

    if hasattr(out, "messages"):
        for msg in getattr(out, "messages"):
            if isinstance(msg, dict):
                content = msg.get("content")
                if content:
                    return str(content)
            elif hasattr(msg, "content"):
                content = getattr(msg, "content")
                if content:
                    return str(content)

    return ""


def _safe_json(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()

    if raw.startswith("```"):
        lines = raw.splitlines()
        lines = lines[1:-1]
        raw = "\n".join(lines)

    try:
        return json.loads(raw)
    except Exception:
        return {}


# -----------------------------------------------------------
# Schema Fetch
# -----------------------------------------------------------


def _fetch_schema(pg: Any, table_name: str) -> List[Dict[str, str]]:
    bare = table_name.split(".")[-1]
    result = pg.describe_table(bare)
    return _parse_csv_rows(result)


# -----------------------------------------------------------
# AI Column Classification
# -----------------------------------------------------------


def _classify_columns_with_agent(
    agent: Optional[Agent],
    table_name: str,
    schema_rows: List[Dict[str, str]],
) -> Dict[str, Any]:

    if agent is None:
        return {
            "business_intent": "generic",
            "business_metric_columns": [],
            "business_dimension_columns": [],
            "business_time_columns": [],
            "technical_columns": [],
        }

    schema_text = "\n".join(
        f"{row.get('column_name')} : {row.get('data_type')}" for row in schema_rows
    )

    prompt = f"""
Table: {table_name}

Columns:
{schema_text}

Classify the schema according to instructions.
Return JSON only.
"""

    try:
        out = agent.run(input=prompt)
        text = _extract_content(out)
        payload = _safe_json(text)

        if payload:
            return payload

    except Exception as e:
        log_error(f"Schema classification agent failed: {e}")

    return {
        "business_intent": "generic",
        "business_metric_columns": [],
        "business_dimension_columns": [],
        "business_time_columns": [],
        "technical_columns": [],
    }


# -----------------------------------------------------------
# Metric Builders
# -----------------------------------------------------------


def _metric_total_records(pg: Any, table: str) -> Dict[str, Any]:

    rows = _parse_csv_rows(
        pg.run_query(f"SELECT COUNT(*) as total_records FROM {table}")
    )

    if not rows:
        return {"title": "Total Records", "value": 0}

    return {
        "title": "Total Records",
        "value": rows[0]["total_records"],
        "unit": None,
        "note": None,
    }


def _metric_sum(pg: Any, table: str, column: str) -> Optional[Dict[str, Any]]:

    query = f"SELECT SUM({column}) as total_value FROM {table}"

    rows = _parse_csv_rows(pg.run_query(query))
    if not rows:
        return None

    return {
        "title": f"Total {column}",
        "value": rows[0]["total_value"],
        "unit": None,
        "note": None,
    }


# -----------------------------------------------------------
# Chart Builders
# -----------------------------------------------------------


def _bar_chart(
    chart_tool: ChartTools,
    title: str,
    x_label: str,
    y_label: str,
    rows: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:

    if not rows:
        return None

    keys = list(rows[0].keys())
    if len(keys) < 2:
        return None

    x = keys[0]
    y = keys[1]

    data: Dict[str, Any] = {}

    for row in rows:
        data[str(row[x])] = row[y]

    if not data:
        return None

    return {
        "title": title,
        "echarts": chart_tool.create_bar_chart(
            data=data,
            title=title,
            x_label=x_label,
            y_label=y_label,
        ),
        "note": None,
    }


def _pie_chart(
    chart_tool: ChartTools,
    title: str,
    rows: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:

    if not rows:
        return None

    keys = list(rows[0].keys())
    if len(keys) < 2:
        return None

    x = keys[0]
    y = keys[1]

    data = {str(r[x]): r[y] for r in rows}

    return {
        "title": title,
        "echarts": chart_tool.create_pie_chart(
            data=data,
            title=title,
        ),
        "note": None,
    }


# -----------------------------------------------------------
# Dashboard Builder
# -----------------------------------------------------------


def build_dashboard(
    table_name: str,
    session_id: str,
    request_id: str,
    summary_agent: Optional[Agent] = None,
) -> Dict[str, Any]:

    pg = get_postgres_tools()
    chart_tool = ChartTools()

    schema_rows = _fetch_schema(pg, table_name)

    classification = _classify_columns_with_agent(
        summary_agent,
        table_name,
        schema_rows,
    )

    business_intent = classification.get("business_intent", "generic")

    metric_cols = classification.get("business_metric_columns", [])
    dimension_cols = classification.get("business_dimension_columns", [])
    time_cols = classification.get("business_time_columns", [])

    metrics: List[Dict[str, Any]] = []
    charts: List[Dict[str, Any]] = []
    tables: List[Dict[str, Any]] = []

    # --------------------------------------------------
    # Metrics
    # --------------------------------------------------

    metrics.append(_metric_total_records(pg, table_name))

    if metric_cols:
        metric = _metric_sum(pg, table_name, metric_cols[0])
        if metric:
            metrics.append(metric)

    # --------------------------------------------------
    # Charts
    # --------------------------------------------------

    if dimension_cols:
        col = dimension_cols[0]

        query = f"""
        SELECT {col}, COUNT(*) as record_count
        FROM {table_name}
        GROUP BY {col}
        ORDER BY record_count DESC
        LIMIT 10
        """

        rows = _parse_csv_rows(pg.run_query(query))

        bar = _bar_chart(
            chart_tool,
            title=f"Distribution by {col}",
            x_label=col,
            y_label="Count",
            rows=rows,
        )

        if bar:
            charts.append(bar)

        pie = _pie_chart(
            chart_tool,
            title=f"{col} Share",
            rows=rows[:6],
        )

        if pie:
            charts.append(pie)

    # --------------------------------------------------
    # Column Descriptions
    # --------------------------------------------------

    column_descriptions: List[str] = []

    for col in metric_cols[:2]:
        column_descriptions.append(
            f"{col} represents a measurable business value useful for KPI tracking."
        )

    for col in dimension_cols[:2]:
        column_descriptions.append(
            f"{col} allows segmentation of business data for deeper analysis."
        )

    for col in time_cols[:1]:
        column_descriptions.append(
            f"{col} enables time-based trend analysis."
        )

    # --------------------------------------------------
    # Final Payload
    # --------------------------------------------------

    payload = {
        "table": table_name,
        "session_id": session_id,
        "business_intent": business_intent,
        "metrics": metrics,
        "charts": charts,
        "tables": tables,
        "column_descriptions": column_descriptions,
        "notes": [],
        "raw": {
            "request_id": request_id,
            "metric_columns": metric_cols,
            "dimension_columns": dimension_cols,
            "time_columns": time_cols,
        },
    }

    log_debug(
        f"DASHBOARD builder_done table={table_name} intent={business_intent} "
        f"metrics={len(metrics)} charts={len(charts)}"
    )

    return payload
