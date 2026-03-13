



def _build_metrics(pg: Any, qtable: str, numeric_cols: List[ColumnInfo], category_cols: List[ColumnInfo]) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = [_metric_total_records(pg, qtable)]

    if numeric_cols:
        metrics.extend(_metric_sum_avg(pg, qtable, numeric_cols[0]))

    if category_cols:
        metrics.append(_metric_distinct(pg, qtable, category_cols[0]))

    return metrics[:5]


def _build_charts(
    pg: Any,
    chart_tool: ChartTools,
    qtable: str,
    numeric_cols: List[ColumnInfo],
    category_cols: List[ColumnInfo],
    time_cols: List[ColumnInfo],
) -> List[Dict[str, Any]]:
    charts: List[Dict[str, Any]] = []

    charts.extend(_build_category_charts(pg, chart_tool, qtable, category_cols))
    charts.extend(_build_time_charts(pg, chart_tool, qtable, numeric_cols, time_cols))
    charts.extend(_build_metric_by_category_chart(pg, chart_tool, qtable, numeric_cols, category_cols))

    return charts[:4]


def _build_category_charts(
    pg: Any,
    chart_tool: ChartTools,
    qtable: str,
    category_cols: List[ColumnInfo],
) -> List[Dict[str, Any]]:
    if not category_cols:
        return []

    rows = _top_category_rows(pg, qtable, category_cols[0])
    results: List[Dict[str, Any]] = []

    bar_chart = _make_bar_chart(
        chart_tool=chart_tool,
        title=f"Top {category_cols[0].name} by record count",
        x_label=category_cols[0].name,
        y_label="Count",
        rows=rows,
    )
    if bar_chart:
        results.append(bar_chart)

    pie_chart = _make_pie_chart(
        chart_tool=chart_tool,
        title=f"{category_cols[0].name} share",
        rows=rows[:6],
    )
    if pie_chart:
        results.append(pie_chart)

    return results


def _build_time_charts(
    pg: Any,
    chart_tool: ChartTools,
    qtable: str,
    numeric_cols: List[ColumnInfo],
    time_cols: List[ColumnInfo],
) -> List[Dict[str, Any]]:
    if not time_cols:
        return []

    rows = _trend_rows(
        pg=pg,
        qtable=qtable,
        time_col=time_cols[0],
        num_col=numeric_cols[0] if numeric_cols else None,
    )

    chart = _make_line_chart(
        chart_tool=chart_tool,
        title=f"Trend by {time_cols[0].name}",
        x_label=time_cols[0].name,
        y_label=numeric_cols[0].name if numeric_cols else "Count",
        rows=rows,
    )

    return [chart] if chart else []


def _build_metric_by_category_chart(
    pg: Any,
    chart_tool: ChartTools,
    qtable: str,
    numeric_cols: List[ColumnInfo],
    category_cols: List[ColumnInfo],
) -> List[Dict[str, Any]]:
    if not numeric_cols or not category_cols:
        return []

    rows = _category_metric_rows(
        pg=pg,
        qtable=qtable,
        cat_col=category_cols[0],
        num_col=numeric_cols[0],
    )

    chart = _make_bar_chart(
        chart_tool=chart_tool,
        title=f"{numeric_cols[0].name} by {category_cols[0].name}",
        x_label=category_cols[0].name,
        y_label=numeric_cols[0].name,
        rows=rows,
    )

    return [chart] if chart else []


def _build_tables(
    pg: Any,
    qtable: str,
    numeric_cols: List[ColumnInfo],
    category_cols: List[ColumnInfo],
    time_cols: List[ColumnInfo],
) -> List[Dict[str, Any]]:
    tables: List[Dict[str, Any]] = []

    top_table = _build_top_category_table(pg, qtable, category_cols)
    if top_table:
        tables.append(top_table)

    missing_table = _build_missing_values_table(pg, qtable, numeric_cols, category_cols, time_cols)
    if missing_table:
        tables.append(missing_table)

    return tables[:2]


def _build_top_category_table(
    pg: Any,
    qtable: str,
    category_cols: List[ColumnInfo],
) -> Optional[Dict[str, Any]]:
    if not category_cols:
        return None

    rows = _top_category_rows(pg, qtable, category_cols[0])
    return _markdown_from_rows(f"Top {category_cols[0].name} Summary", rows)


def _build_missing_values_table(
    pg: Any,
    qtable: str,
    numeric_cols: List[ColumnInfo],
    category_cols: List[ColumnInfo],
    time_cols: List[ColumnInfo],
) -> Optional[Dict[str, Any]]:
    important_cols: List[ColumnInfo] = []
    important_cols.extend(numeric_cols[:2])
    important_cols.extend(category_cols[:2])
    important_cols.extend(time_cols[:1])

    return _missing_values_table(pg, qtable, important_cols)
---------
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
    category_cols = _pick_category_columns(columns)
    time_cols = _pick_time_columns(columns)

    metrics = _build_metrics(pg, qtable, numeric_cols, category_cols)
    charts = _build_charts(pg, chart_tool, qtable, numeric_cols, category_cols, time_cols)
    tables = _build_tables(pg, qtable, numeric_cols, category_cols, time_cols)
    column_descriptions = _build_column_descriptions(numeric_cols, category_cols, time_cols)

    payload: Dict[str, Any] = {
        "table": table_name,
        "session_id": session_id,
        "metrics": metrics,
        "charts": charts,
        "tables": tables,
        "column_descriptions": column_descriptions,
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

    --------------------------------------------------------------------------------------
jgfcgjfc

    

    return payload
