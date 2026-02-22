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


------------------------------

_FENCE_RE = re.compile(
    r"```(?:json|echarts)\s*([\s\S]*?)\s*```",
    re.IGNORECASE,
)

def _extract_graph_json_from_reply(reply: str) -> tuple[str, Optional[str]]:
    """
    Extract a fenced block either ```json ...``` or ```echarts ...```
    Returns (clean_reply, graph_json_string_or_none).

    IMPORTANT: returns JSON as STRING (since your frontend expects json.dumps(graph_json) and tools already do json.dumps).
    """
    if not reply:
        return reply, None

    m = _FENCE_RE.search(reply)
    if not m:
        return reply, None

    blob = (m.group(1) or "").strip()
    if not blob:
        return reply, None

    # Validate if possible; but even if invalid, still return it (better than losing it)
    try:
        json.loads(blob)
        json_blob = blob
    except Exception:
        # Sometimes models put "option = {...}" or extra text; try to extract first {...} or [...]
        m2 = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", blob)
        if m2:
            candidate = m2.group(1).strip()
            try:
                json.loads(candidate)
                json_blob = candidate
            except Exception:
                # still return raw blob
                json_blob = blob
        else:
            json_blob = blob

    clean_reply = _FENCE_RE.sub("", reply).strip()
    return clean_reply, json_blob

    -----------------------------

out = team.run(input=final_prompt, session_id=session_id)

raw_reply = _extract_team_content(out)

# If still empty, try a last-resort stringification (some RunOutputs stringify nicely)
if not raw_reply.strip():
    raw_reply = str(out) if out is not None else ""

clean_reply, graph_json = _extract_graph_json_from_reply(raw_reply)

# Ensure reply is always meaningful
reply = clean_reply if clean_reply.strip() else raw_reply

agent_used = extract_agent_used(out)

structured_output = None
if graph_json is not None and str(graph_json).strip():
    structured_output = {"graph_json": str(graph_json)}
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
