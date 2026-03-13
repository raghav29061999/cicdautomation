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
from src.tools import ChartTools


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

    def _collect(value: Any) -> None:
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
        _collect(getattr(out, "content", None))

    if hasattr(out, "messages"):
        msgs = getattr(out, "messages", None)
        if isinstance(msgs, list):
            for msg in msgs:
                if isinstance(msg, dict):
                    _collect(msg.get("content"))
                elif hasattr(msg, "content"):
                    _collect(getattr(msg, "content", None))
                else:
                    _collect(msg)

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
    lowered = col.name.lower()
    return any(token in lowered for token in TECH_SUBSTRINGS)


def _score_name(name: str, preferred: tuple[str, ...]) -> int:
    lowered = name.lower()
    for idx, token in enumerate(preferred):
        if token in lowered:
            return idx
    return 999


def _parse_schema(pg: Any, table_name: str) -> List[ColumnInfo]:
    bare_table = table_name.split(".")[-1]
    rows = _parse_csv_rows(pg.describe_table(bare_table))

    parsed: List[ColumnInfo] = []
    for row in rows:
        parsed.append(
            ColumnInfo(
                name=str(row.get("column_name") or "").strip(),
                data_type=str(row.get("data_type") or "").strip().lower(),
                is_nullable=str(row.get("is_nullable") or "").strip(),
            )
        )
    return parsed


def _pick_numeric_columns(columns: List[ColumnInfo]) -> List[ColumnInfo]:
    items = [c for c in columns if c.data_type in NUMERIC_TYPES and not _is_technical(c)]
    return sorted(items, key=lambda c: _score_name(c.name, PREFERRED_NUMERIC_NAMES))


def _pick_time_columns(columns: List[ColumnInfo]) -> List[ColumnInfo]:
    items = [c for c in columns if c.data_type in TIME_TYPES and not _is_technical(c)]
    return sorted(items, key=lambda c: _score_name(c.name, PREFERRED_TIME_NAMES))


def _pick_category_columns(columns: List[ColumnInfo]) -> List[ColumnInfo]:
    items: List[ColumnInfo] = []
    for col in columns:
        if _is_technical(col):
            continue
        if col.data_type in NUMERIC_TYPES or col.data_type in TIME_TYPES:
            continue
        items.append(col)
    return sorted(items, key=lambda c: _score_name(c.name, PREFERRED_CATEGORY_NAMES))


def _run_rows(pg: Any, query: str) -> List[Dict[str, str]]:
    return _parse_csv_rows(pg.run_query(query))


def _run_scalar(pg: Any, query: str) -> str:
    rows = _run_rows(pg, query)
    if not rows:
        return ""
    first = rows[0]
    if not first:
        return ""
    return str(next(iter(first.values())))


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
        f"SELECT COALESCE(SUM({qcol}), 0) AS total_value, "
        f"COALESCE(AVG({qcol}), 0) AS avg_value "
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
            f"SELECT COUNT(DISTINCT {qcol}) AS distinct_count "
            f"FROM {qtable} WHERE {qcol} IS NOT NULL",
        )
    )
    return {
        "title": f"Distinct {col.name}",
        "value": value,
        "unit": None,
        "note": None,
    }


def _rows_to_dict_data(rows: List[Dict[str, str]]) -> Dict[str, int | float | str]:
    if not rows:
        return {}

    keys = list(rows[0].keys())
    if len(keys) < 2:
        return {}

    x_key, y_key = keys[0], keys[1]
    out: Dict[str, int | float | str] = {}

    for row in rows:
        label = str(row.get(x_key) or "").strip()
        if not label:
            continue
        out[label] = _to_number(row.get(y_key))

    return out


def _make_bar_chart(
    chart_tool: ChartTools,
    title: str,
    x_label: str,
    y_label: str,
    rows: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    data = _rows_to_dict_data(rows)
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


def _make_line_chart(
    chart_tool: ChartTools,
    title: str,
    x_label: str,
    y_label: str,
    rows: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    data = _rows_to_dict_data(rows)
    if not data:
        return None

    return {
        "title": title,
        "echarts": chart_tool.create_line_chart(
            data=data,
            title=title,
            x_label=x_label,
            y_label=y_label,
        ),
        "note": None,
    }


def _make_pie_chart(
    chart_tool: ChartTools,
    title: str,
    rows: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    data = _rows_to_dict_data(rows)
    if not data:
        return None

    return {
        "title": title,
        "echarts": chart_tool.create_pie_chart(
            data=data,
            title=title,
        ),
        "note": None,
    }


def _top_category_rows(pg: Any, qtable: str, col: ColumnInfo) -> List[Dict[str, str]]:
    qcol = _quote_ident(col.name)
    query = (
        f"SELECT {qcol} AS category, COUNT(*) AS record_count "
        f"FROM {qtable} "
        f"WHERE {qcol} IS NOT NULL "
        f"GROUP BY {qcol} "
        f"ORDER BY record_count DESC "
        f"LIMIT 10"
    )
    return _run_rows(pg, query)


def _trend_rows(
    pg: Any,
    qtable: str,
    time_col: ColumnInfo,
    num_col: Optional[ColumnInfo],
) -> List[Dict[str, str]]:
    qtime = _quote_ident(time_col.name)

    if num_col is not None:
        qnum = _quote_ident(num_col.name)
        metric_expr = f"COALESCE(SUM({qnum}), 0)"
        metric_alias = "metric_value"
    else:
        metric_expr = "COUNT(*)"
        metric_alias = "record_count"

    query = (
        f"SELECT DATE_TRUNC('month', {qtime})::date AS period, "
        f"{metric_expr} AS {metric_alias} "
        f"FROM {qtable} "
        f"WHERE {qtime} IS NOT NULL "
        f"GROUP BY period "
        f"ORDER BY period "
        f"LIMIT 24"
    )
    return _run_rows(pg, query)


def _category_metric_rows(
    pg: Any,
    qtable: str,
    cat_col: ColumnInfo,
    num_col: ColumnInfo,
) -> List[Dict[str, str]]:
    qcat = _quote_ident(cat_col.name)
    qnum = _quote_ident(num_col.name)
    query = (
        f"SELECT {qcat} AS category, COALESCE(SUM({qnum}), 0) AS metric_total "
        f"FROM {qtable} "
        f"WHERE {qcat} IS NOT NULL "
        f"GROUP BY {qcat} "
        f"ORDER BY metric_total DESC "
        f"LIMIT 10"
    )
    return _run_rows(pg, query)


def _markdown_from_rows(title: str, rows: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    if not rows:
        return None

    headers = list(rows[0].keys())
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]

    for row in rows:
        lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")

    return {"title": title, "markdown": "\n".join(lines), "note": None}


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
        missing_pct = round((missing / total) * 100, 2) if total else 0.0

        rows_out.append(
            {
                "column_name": col.name,
                "missing_count": str(missing),
                "missing_pct": str(missing_pct),
            }
        )

    return _markdown_from_rows("Missing Values Summary", rows_out)


def _build_column_descriptions(
    numeric_cols: List[ColumnInfo],
    category_cols: List[ColumnInfo],
    time_cols: List[ColumnInfo],
) -> List[str]:
    descriptions: List[str] = []

    for col in numeric_cols[:2]:
        descriptions.append(
            f"{col.name}: numeric business measure suitable for totals, averages, and contribution analysis."
        )

    for col in category_cols[:2]:
        descriptions.append(
            f"{col.name}: categorical business dimension suitable for segmentation and top-N breakdowns."
        )

    for col in time_cols[:1]:
        descriptions.append(
            f"{col.name}: time dimension suitable for trend and seasonality analysis."
        )

    return descriptions


def _deterministic_notes(
    metrics: List[Dict[str, Any]],
    charts: List[Dict[str, Any]],
    tables: List[Dict[str, Any]],
) -> List[str]:
    notes: List[str] = []

    if metrics:
        notes.append(f"{len(metrics)} key metrics were generated from the selected table.")
    if charts:
        notes.append(f"{len(charts)} visual summaries were generated for business exploration.")
    if tables:
        notes.append(f"{len(tables)} supporting markdown tables were included for quick inspection.")

    return notes[:4]


def _ai_notes(summary_agent: Optional[Agent], payload: Dict[str, Any]) -> List[str]:
    if summary_agent is None:
        return _deterministic_notes(payload["metrics"], payload["charts"], payload["tables"])

    prompt = (
        "Generate short business notes from these dashboard facts.\n"
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
    chart_tool = ChartTools()

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

        bar_chart = _make_bar_chart(
            chart_tool=chart_tool,
            title=f"Top {category_cols[0].name} by record count",
            x_label=category_cols[0].name,
            y_label="Count",
            rows=top_rows,
        )
        if bar_chart:
            charts.append(bar_chart)

        pie_chart = _make_pie_chart(
            chart_tool=chart_tool,
            title=f"{category_cols[0].name} share",
            rows=top_rows[:6],
        )
        if pie_chart:
            charts.append(pie_chart)

    if time_cols:
        trend = _trend_rows(
            pg=pg,
            qtable=qtable,
            time_col=time_cols[0],
            num_col=numeric_cols[0] if numeric_cols else None,
        )
        line_chart = _make_line_chart(
            chart_tool=chart_tool,
            title=f"Trend by {time_cols[0].name}",
            x_label=time_cols[0].name,
            y_label=numeric_cols[0].name if numeric_cols else "Count",
            rows=trend,
        )
        if line_chart:
            charts.append(line_chart)

    if numeric_cols and category_cols:
        combo_rows = _category_metric_rows(
            pg=pg,
            qtable=qtable,
            cat_col=category_cols[0],
            num_col=numeric_cols[0],
        )
        combo_chart = _make_bar_chart(
            chart_tool=chart_tool,
            title=f"{numeric_cols[0].name} by {category_cols[0].name}",
            x_label=category_cols[0].name,
            y_label=numeric_cols[0].name,
            rows=combo_rows,
        )
        if combo_chart:
            charts.append(combo_chart)

    charts = charts[:4]

    tables: List[Dict[str, Any]] = []

    if category_cols:
        top_rows = _top_category_rows(pg, qtable, category_cols[0])
        top_table = _markdown_from_rows(
            title=f"Top {category_cols[0].name} Summary",
            rows=top_rows,
        )
        if top_table:
            tables.append(top_table)

    important_cols: List[ColumnInfo] = []
    important_cols.extend(numeric_cols[:2])
    important_cols.extend(category_cols[:2])
    important_cols.extend(time_cols[:1])

    missing_table = _missing_values_table(pg, qtable, important_cols)
    if missing_table:
        tables.append(missing_table)

    tables = tables[:2]

    payload: Dict[str, Any] = {
        "table": table_name,
        "session_id": session_id,
        "metrics": metrics,
        "charts": charts,
        "tables": tables,
        "column_descriptions": _build_column_descriptions(numeric_cols, category_cols, time_cols),
        "notes": [],
        "raw": {
            "request_id": request_id,
            "numeric_columns": [col.name for col in numeric_cols],
            "category_columns": [col.name for col in category_cols],
            "time_columns": [col.name for col in time_cols],
        },
    }

    payload["notes"] = _ai_notes(summary_agent, payload)

    log_debug(
        f"DASHBOARD builder_done table={table_name} "
        f"metrics={len(payload['metrics'])} charts={len(payload['charts'])} "
        f"tables={len(payload['tables'])}"
    )

    return payload
