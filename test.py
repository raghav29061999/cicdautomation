def _extract_team_content(out: Any) -> str:
    """
    Normalize outputs from Agno Team/RunOutput across versions.
    We try multiple common fields and shapes.
    """
    if out is None:
        return ""

    # 1) Most common: .content
    if hasattr(out, "content"):
        c = getattr(out, "content")
        if c is None:
            pass
        elif isinstance(c, str):
            return c
        elif isinstance(c, dict):
            # Sometimes content is structured dict
            for k in ("reply", "text", "message", "output", "content"):
                v = c.get(k)
                if isinstance(v, str) and v.strip():
                    return v
            # fallback to stringify
            return json.dumps(c, ensure_ascii=False)
        else:
            # pydantic model or other object
            try:
                return str(c)
            except Exception:
                pass

    # 2) Other common attributes
    for attr in ("output", "text", "message", "reply"):
        if hasattr(out, attr):
            v = getattr(out, attr)
            if isinstance(v, str) and v.strip():
                return v

    # 3) If it has messages (list), try the last one
    if hasattr(out, "messages"):
        msgs = getattr(out, "messages")
        if isinstance(msgs, list) and msgs:
            last = msgs[-1]
            if isinstance(last, str):
                return last
            if isinstance(last, dict):
                for k in ("content", "text", "message"):
                    v = last.get(k)
                    if isinstance(v, str) and v.strip():
                        return v
            try:
                return str(last)
            except Exception:
                pass

    # 4) Fallback
    try:
        return str(out)
    except Exception:
        return ""
