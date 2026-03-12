def _build_agent_input(table: str) -> str:
    return (
        "[CONTEXT]\n"
        f"selected_table={table}\n"
        "[/CONTEXT]\n\n"
        "Generate a default business dashboard for selected_table.\n"
        "You MUST call describe_table(selected_table) first to understand schema.\n"
        "Use postgres tools to compute real values for metrics.\n"
        "Use chart tools to create 2 to 4 meaningful business charts.\n"
        "Use data quality tools only if they add business value.\n"
        "Ignore technical, metadata, ingestion, audit, and system-generated columns.\n"
        "Focus on business-relevant columns such as amount, revenue, quantity, category, status, customer, product, region, and date/time columns.\n"
        "Generate:\n"
        "- 3 to 5 metrics\n"
        "- 2 to 4 charts\n"
        "- 0 to 2 markdown tables\n"
        "- 2 to 5 short notes\n"
        "Return ONLY valid JSON in this format:\n"
        "{\n"
        '  "table": "<schema.table>",\n'
        '  "metrics": [{"title": "...", "value": 123, "unit": null, "note": "..."}],\n'
        '  "charts": [{"title": "...", "echarts": "...", "note": "..."}],\n'
        '  "tables": [{"title": "...", "markdown": "...", "note": "..."}],\n'
        '  "notes": ["..."]\n'
        "}\n"
        "Do not return empty arrays unless absolutely no meaningful result can be generated."
    )
