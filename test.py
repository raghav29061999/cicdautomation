if not response["metrics"] and not response["charts"] and not response["tables"] and not response["notes"]:
    raise ValueError("Dashboard agent returned an empty dashboard")

-----------------------------
log_debug(
    f"DASHBOARD parsed_payload request_id={request_id} session_id={sid} "
    f"metrics={len(payload.get('metrics', []) or [])} "
    f"charts={len(payload.get('charts', []) or [])} "
    f"tables={len(payload.get('tables', []) or [])} "
    f"notes={len(payload.get('notes', []) or [])}"
)
