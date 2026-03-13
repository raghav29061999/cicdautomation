BUSINESS_METRIC_HINTS = (
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
    "balance",
    "score",
    "rating",
    "discount",
    "payment",
    "charge",
)

BUSINESS_DIMENSION_HINTS = (
    "status",
    "category",
    "type",
    "region",
    "segment",
    "product",
    "customer",
    "country",
    "city",
    "state",
    "channel",
    "brand",
    "department",
    "priority",
)

TECHNICAL_HINTS = (
    "id",
    "uuid",
    "hash",
    "file",
    "source",
    "created",
    "updated",
    "ingest",
    "batch",
    "record",
    "flag",
    "metadata",
    "audit",
)

TRANSACTION_HINTS = (
    "amount",
    "payment",
    "transaction",
    "order",
    "invoice",
    "sales",
    "price",
    "revenue",
)

CUSTOMER_HINTS = (
    "customer",
    "client",
    "user",
    "account",
    "signup",
    "region",
    "segment",
)

INVENTORY_HINTS = (
    "product",
    "inventory",
    "stock",
    "sku",
    "brand",
    "category",
    "warehouse",
)

SUPPORT_HINTS = (
    "ticket",
    "issue",
    "priority",
    "resolution",
    "agent",
    "sla",
    "status",
)


---------------------------------------------------------------------------------------------------------------------
<replace>
def _is_technical(col: ColumnInfo) -> bool:
    lowered = col.name.lower()

    if lowered in {"id", "record_id", "row_id"}:
        return True

    if any(token in lowered for token in TECHNICAL_HINTS):
        # allow some business-like exceptions
        if any(token in lowered for token in ("customer_id", "product_id", "order_id", "transaction_id")):
            return False
        return True

    return False

--------------------------------------------------------------------------------------------

def _business_score(col: ColumnInfo) -> int:
    name = col.name.lower()
    score = 0

    if _is_technical(col):
        return -100

    if any(token in name for token in BUSINESS_METRIC_HINTS):
        score += 10

    if any(token in name for token in BUSINESS_DIMENSION_HINTS):
        score += 8

    if any(token in name for token in PREFERRED_TIME_NAMES):
        score += 6

    if col.data_type in NUMERIC_TYPES:
        score += 3

    if col.data_type in TIME_TYPES:
        score += 4

    # discourage generic ids even if numeric
    if name == "id" or name.endswith("_id"):
        score -= 8

    return score


------------------------------
<replace>
def _pick_numeric_columns(columns: List[ColumnInfo]) -> List[ColumnInfo]:
    numeric = [c for c in columns if c.data_type in NUMERIC_TYPES and not _is_technical(c)]
    numeric = [c for c in numeric if _business_score(c) > 0]
    return sorted(
        numeric,
        key=lambda c: (_score_name(c.name, PREFERRED_NUMERIC_NAMES), -_business_score(c)),
    )

def _pick_time_columns(columns: List[ColumnInfo]) -> List[ColumnInfo]:
    time_cols = [c for c in columns if c.data_type in TIME_TYPES and not _is_technical(c)]
    return sorted(
        time_cols,
        key=lambda c: (_score_name(c.name, PREFERRED_TIME_NAMES), -_business_score(c)),
    )

def _pick_category_columns(columns: List[ColumnInfo]) -> List[ColumnInfo]:
    categories: List[ColumnInfo] = []

    for col in columns:
        if _is_technical(col):
            continue
        if col.data_type in NUMERIC_TYPES or col.data_type in TIME_TYPES:
            continue
        if _business_score(col) <= 0:
            continue
        categories.append(col)

    return sorted(
        categories,
        key=lambda c: (_score_name(c.name, PREFERRED_CATEGORY_NAMES), -_business_score(c)),
    )
--------------------------

def _infer_table_intent(columns: List[ColumnInfo]) -> str:
    names = " ".join(col.name.lower() for col in columns)

    if any(token in names for token in TRANSACTION_HINTS):
        return "transaction"

    if any(token in names for token in CUSTOMER_HINTS):
        return "customer"

    if any(token in names for token in INVENTORY_HINTS):
        return "inventory"

    if any(token in names for token in SUPPORT_HINTS):
        return "support"

    return "generic"

----------------------------------------

def _build_metrics_by_intent(
    pg: Any,
    qtable: str,
    numeric_cols: List[ColumnInfo],
    category_cols: List[ColumnInfo],
    time_cols: List[ColumnInfo],
    intent: str,
) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = [_metric_total_records(pg, qtable)]

    if intent == "transaction":
        if numeric_cols:
            metrics.extend(_metric_sum_avg(pg, qtable, numeric_cols[0]))
        if category_cols:
            metrics.append(_metric_distinct(pg, qtable, category_cols[0]))

    elif intent == "customer":
        if category_cols:
            metrics.append(_metric_distinct(pg, qtable, category_cols[0]))
        if time_cols:
            metrics.append(
                {
                    "title": "Active Time Dimension",
                    "value": time_cols[0].name,
                    "unit": None,
                    "note": "Primary time field available for trend analysis",
                }
            )

    elif intent == "inventory":
        if numeric_cols:
            metrics.extend(_metric_sum_avg(pg, qtable, numeric_cols[0]))
        if category_cols:
            metrics.append(_metric_distinct(pg, qtable, category_cols[0]))

    elif intent == "support":
        if category_cols:
            metrics.append(_metric_distinct(pg, qtable, category_cols[0]))
        if time_cols:
            metrics.append(
                {
                    "title": "Trend Field",
                    "value": time_cols[0].name,
                    "unit": None,
                    "note": "Used for ticket / issue trend analysis",
                }
            )

    else:
        if numeric_cols:
            metrics.extend(_metric_sum_avg(pg, qtable, numeric_cols[0]))
        if category_cols:
            metrics.append(_metric_distinct(pg, qtable, category_cols[0]))

    return metrics[:5]


------------------------

replace

def _build_charts(
    pg: Any,
    chart_tool: ChartTools,
    qtable: str,
    numeric_cols: List[ColumnInfo],
    category_cols: List[ColumnInfo],
    time_cols: List[ColumnInfo],
    intent: str,
) -> List[Dict[str, Any]]:
    charts: List[Dict[str, Any]] = []

    if category_cols:
        charts.extend(_build_category_charts(pg, chart_tool, qtable, category_cols))

    if time_cols:
        charts.extend(_build_time_charts(pg, chart_tool, qtable, numeric_cols, time_cols))

    if numeric_cols and category_cols and intent in {"transaction", "inventory", "generic"}:
        charts.extend(_build_metric_by_category_chart(pg, chart_tool, qtable, numeric_cols, category_cols))

    return charts[:4]


-------------------------

replace
def _build_column_descriptions(
    numeric_cols: List[ColumnInfo],
    category_cols: List[ColumnInfo],
    time_cols: List[ColumnInfo],
    intent: str,
) -> List[str]:
    descriptions: List[str] = []

    if intent == "transaction":
        for col in numeric_cols[:2]:
            descriptions.append(f"{col.name}: key transaction measure useful for tracking volume, value, and performance.")
        for col in category_cols[:2]:
            descriptions.append(f"{col.name}: business breakdown dimension useful for contribution and mix analysis.")
        for col in time_cols[:1]:
            descriptions.append(f"{col.name}: time field used to understand business trends over time.")

    elif intent == "customer":
        for col in category_cols[:2]:
            descriptions.append(f"{col.name}: customer segmentation field useful for understanding user groups.")
        for col in time_cols[:1]:
            descriptions.append(f"{col.name}: customer lifecycle or activity time field.")

    elif intent == "inventory":
        for col in numeric_cols[:2]:
            descriptions.append(f"{col.name}: inventory or product quantity/value measure.")
        for col in category_cols[:2]:
            descriptions.append(f"{col.name}: product grouping field useful for stock/category analysis.")

    elif intent == "support":
        for col in category_cols[:2]:
            descriptions.append(f"{col.name}: ticket or issue classification field useful for operational monitoring.")
        for col in time_cols[:1]:
            descriptions.append(f"{col.name}: time field useful for issue trend tracking.")

    else:
        for col in numeric_cols[:2]:
            descriptions.append(f"{col.name}: business numeric field useful for summary analysis.")
        for col in category_cols[:2]:
            descriptions.append(f"{col.name}: business grouping field useful for segmentation.")
        for col in time_cols[:1]:
            descriptions.append(f"{col.name}: time field useful for trend analysis.")

    return descriptions

----------------

intent = _infer_table_intent(columns)




metrics = _build_metrics_by_intent(pg, qtable, numeric_cols, category_cols, time_cols, intent)
charts = _build_charts(pg, chart_tool, qtable, numeric_cols, category_cols, time_cols, intent)
column_descriptions = _build_column_descriptions(numeric_cols, category_cols, time_cols, intent)
