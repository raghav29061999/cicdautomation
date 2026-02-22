_JSON_FENCE_RE = re.compile(
    r"```json\s*(\{.*?\}|\[.*?\])\s*```",
    re.DOTALL | re.IGNORECASE,
)

def _extract_graph_json_from_reply(reply: str) -> tuple[str, Optional[str]]:
    """
    Returns (clean_reply, graph_json_string_or_none).

    - If reply contains ```json ... ``` block, extract it.
    - graph_json is returned as a *string* (exactly what your frontend/tool expects).
    """
    if not reply:
        return reply, None

    m = _JSON_FENCE_RE.search(reply)
    if not m:
        return reply, None

    json_blob = (m.group(1) or "").strip()

    # Validate that it is actually JSON (but keep it as string)
    try:
        json.loads(json_blob)
    except Exception:
        # If it isn't valid JSON, don't claim it is
        return reply, None

    # Remove the fenced block from reply for cleaner chat text
    clean_reply = _JSON_FENCE_RE.sub("", reply).strip()
    return clean_reply, json_blob

-----------------------------------


out = team.run(input=final_prompt, session_id=session_id)

raw_reply = _extract_team_content(out)
clean_reply, graph_json = _extract_graph_json_from_reply(raw_reply)

reply = clean_reply or raw_reply
agent_used = extract_agent_used(out)

structured_output = None
if graph_json is not None:
    structured_output = {
        "graph_json": graph_json  # ✅ string JSON, no fences
    }

-----------------------


store.add(
    type="chat_response",
    session_id=session_id,
    payload={
        "agent_used": agent_used,
        "reply": reply,
        "structured_output": structured_output,
        "table_name": selected_table,
    },
)


----------------

return ChatResponse(
    session_id=session_id,
    agent_used=agent_used,
    reply=reply,
    structured_output=structured_output,
    raw={
        "selected_table": selected_table,
        "metadata": metadata,
    },
)
