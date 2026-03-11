def _extract_text_from_any(out: Any) -> str:
    if out is None:
        return ""

    # 1. Try extracting from .content
    text = _extract_from_content(out)
    if text:
        return text

    # 2. Try common attributes
    text = _extract_from_attrs(out)
    if text:
        return text

    # 3. Try message list
    text = _extract_from_messages(out)
    if text:
        return text

    return _safe_str(out)


def _extract_from_content(out: Any) -> str:
    if not hasattr(out, "content"):
        return ""

    c = getattr(out, "content", None)

    if isinstance(c, str) and c.strip():
        return c

    if isinstance(c, dict):
        for k in ("reply", "text", "message", "output", "content"):
            v = c.get(k)
            if isinstance(v, str) and v.strip():
                return v
        return json.dumps(c, ensure_ascii=False)

    if c is not None:
        s = _safe_str(c)
        if s.strip():
            return s

    return ""

def _extract_from_attrs(out: Any) -> str:
    for attr in ("output", "text", "message", "reply"):
        if hasattr(out, attr):
            v = getattr(out, attr, None)
            if isinstance(v, str) and v.strip():
                return v
    return ""

def _extract_from_messages(out: Any) -> str:
    if not hasattr(out, "messages"):
        return ""

    msgs = getattr(out, "messages", None)
    if not isinstance(msgs, list) or not msgs:
        return ""

    last = msgs[-1]

    if isinstance(last, str) and last.strip():
        return last

    if isinstance(last, dict):
        for k in ("content", "text", "message"):
            v = last.get(k)
            if isinstance(v, str) and v.strip():
                return v
        return json.dumps(last, ensure_ascii=False)

    s = _safe_str(last)
    return s if s.strip() else ""
