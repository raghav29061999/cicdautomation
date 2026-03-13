def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False).strip()
        except Exception:
            return str(value).strip()
    return str(value).strip()


def _collect_top_level_content(out: Any) -> List[str]:
    if not hasattr(out, "content"):
        return []
    text = _to_text(getattr(out, "content", None))
    return [text] if text else []


def _collect_message_content(msg: Any) -> str:
    if isinstance(msg, dict):
        return _to_text(msg.get("content"))
    if hasattr(msg, "content"):
        return _to_text(getattr(msg, "content", None))
    return _to_text(msg)


def _collect_messages_content(out: Any) -> List[str]:
    if not hasattr(out, "messages"):
        return []

    msgs = getattr(out, "messages", None)
    if not isinstance(msgs, list):
        return []

    collected: List[str] = []
    for msg in msgs:
        text = _collect_message_content(msg)
        if text:
            collected.append(text)
    return collected


def _pick_best_candidate(candidates: List[str]) -> str:
    if not candidates:
        return ""

    for candidate in reversed(candidates):
        if '"notes"' in candidate:
            return candidate

    return candidates[-1]


def _extract_content(out: Any) -> str:
    candidates = []
    candidates.extend(_collect_top_level_content(out))
    candidates.extend(_collect_messages_content(out))
    return _pick_best_candidate(candidates)
