def _extract_content(out: Any) -> str:
    """
    Robust extractor for Agno RunOutput.

    Strategy:
    1. Try top-level out.content
    2. Scan messages in reverse and return the last non-empty content
    3. Fallback to string conversion
    """
    if out is None:
        return ""

    # 1) Top-level content
    if hasattr(out, "content"):
        c = getattr(out, "content", None)
        if c is not None:
            if isinstance(c, str) and c.strip():
                return c
            if isinstance(c, dict):
                import json
                return json.dumps(c, ensure_ascii=False)
            s = str(c)
            if s.strip():
                return s

    # 2) Scan messages from last to first
    if hasattr(out, "messages"):
        msgs = getattr(out, "messages", None)
        if isinstance(msgs, list):
            for msg in reversed(msgs):
                # dict-like message
                if isinstance(msg, dict):
                    c = msg.get("content")
                    if c is not None and str(c).strip():
                        return str(c)

                # object-like message
                if hasattr(msg, "content"):
                    c = getattr(msg, "content", None)
                    if c is not None and str(c).strip():
                        return str(c)

    # 3) Fallback
    try:
        s = str(out)
        return s if s.strip() else ""
    except Exception:
        return ""


----------------
print("TOP LEVEL CONTENT:", repr(getattr(out, "content", None)))

if hasattr(out, "messages") and out.messages:
    for i, msg in enumerate(out.messages):
        if isinstance(msg, dict):
            print(f"MSG {i} DICT CONTENT:", repr(msg.get("content")))
        else:
            print(f"MSG {i} OBJ CONTENT:", repr(getattr(msg, "content", None)))
