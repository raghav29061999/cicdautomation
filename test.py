def _extract_content(out: Any) -> str:
    """
    Robust extractor for dashboard agent output.
    Searches top-level content first, then scans all messages for the
    most likely final dashboard JSON payload.
    """
    if out is None:
        return ""

    candidates: list[str] = []

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
                import json
                candidates.append(json.dumps(value, ensure_ascii=False))
            except Exception:
                candidates.append(str(value))
            return
        s = str(value).strip()
        if s:
            candidates.append(s)

    # 1) top-level content
    if hasattr(out, "content"):
        _collect(getattr(out, "content", None))

    # 2) all messages, not just last
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

    # Prefer dashboard-like payloads first
    dashboard_keys = ('"metrics"', '"charts"', '"tables"', '"notes"', '"table"')
    for c in reversed(candidates):
        if any(k in c for k in dashboard_keys):
            return c

    # Then prefer anything that looks like JSON
    for c in reversed(candidates):
        s = c.strip()
        if s.startswith("{") or s.startswith("```"):
            return c

    # Final fallback
    return candidates[-1]



-------------------------------------------------------------------------------------------------------------------


def _safe_json_loads(s: str) -> Dict[str, Any]:
    """
    Parse dashboard agent output into a JSON object.
    Handles:
    - raw JSON
    - fenced JSON
    - extra explanatory text before/after JSON
    """
    import json
    import re

    raw = (s or "").strip()
    if not raw:
        raise ValueError("Dashboard agent returned empty content")

    # Strip fenced block if present
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    if raw.lower().startswith("json"):
        raw = raw[4:].strip()

    # Try direct parse first
    try:
        obj = json.loads(raw)
        if obj is None or not isinstance(obj, dict):
            raise ValueError("Dashboard agent did not return a JSON object")
        return obj
    except Exception:
        pass

    # Extract first JSON object from noisy text
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError("No JSON object found in dashboard agent output")

    obj = json.loads(match.group(0))
    if obj is None or not isinstance(obj, dict):
        raise ValueError("Dashboard agent did not return a JSON object")
    return obj


---------------------------------------------------------------------------


def _normalize_echarts(value: Any) -> Dict[str, Any] | str:
    import json

    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return {}

        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines).strip()

        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
        if raw.lower().startswith("echarts"):
            raw = raw[7:].strip()

        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else raw
        except Exception:
            return raw

    return str(value)


def _normalize_metrics(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []

    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append({
            "title": str(item.get("title") or "Metric"),
            "value": item.get("value", ""),
            "unit": None if item.get("unit") is None else str(item.get("unit")),
            "note": None if item.get("note") is None else str(item.get("note")),
        })
    return out


def _normalize_charts(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []

    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        raw_chart = item.get("echarts")
        if raw_chart is None:
            raw_chart = item.get("echart")

        out.append({
            "title": str(item.get("title") or "Chart"),
            "echarts": _normalize_echarts(raw_chart),
            "note": None if item.get("note") is None else str(item.get("note")),
        })
    return out


def _normalize_tables(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []

    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append({
            "title": str(item.get("title") or "Table"),
            "markdown": str(item.get("markdown") or ""),
            "note": None if item.get("note") is None else str(item.get("note")),
        })
    return out


def _normalize_notes(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(x) for x in items if str(x).strip()]

---------------------------------------------------------------

def _build_response(
    table: str,
    sid: str,
    request_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    response = {
        "table": str(payload.get("table") or table),
        "session_id": sid,
        "metrics": _normalize_metrics(payload.get("metrics")),
        "charts": _normalize_charts(payload.get("charts")),
        "tables": _normalize_tables(payload.get("tables")),
        "notes": _normalize_notes(payload.get("notes")),
        "raw": {"request_id": request_id},
    }

    # Ensure at least something meaningful came back
    if (
        not response["metrics"]
        and not response["charts"]
        and not response["tables"]
        and not response["notes"]
    ):
        raise ValueError("Dashboard agent returned an empty dashboard payload")

    return response


--------------------------------------------------------------------


