def _extract_structured_output(out: Any) -> Optional[Dict[str, Any]]:
    """
    Agno-native path: if output_schema is used, Agno returns a typed Pydantic object
    (often in out.content on newer docs), or may expose it via structured_output depending on version.

    We handle both without breaking.
    """
    if out is None:
        return None

    # Newer docs: structured output is returned as a typed object in response.content :contentReference[oaicite:4]{index=4}
    content = getattr(out, "content", None)
    if content is not None:
        if isinstance(content, dict):
            return content
        if hasattr(content, "model_dump"):
            try:
                return content.model_dump()
            except Exception:
                pass

    # Some versions expose it explicitly
    so = getattr(out, "structured_output", None)
    if so is not None:
        if isinstance(so, dict):
            return so
        if hasattr(so, "model_dump"):
            try:
                return so.model_dump()
            except Exception:
                pass

    return None









-----------------











def _extract_json_fence(text: str) -> Optional[Dict[str, Any]]:
    """
    If reply contains a fenced JSON block:
      ```json
      {...}
      ```
    extract and parse it.
    """
    if not text:
        return None

    s = text.strip()
    marker = "```json"
    if marker not in s:
        return None

    try:
        start = s.index(marker) + len(marker)
        end = s.index("```", start)
        blob = s[start:end].strip()
        obj = json.loads(blob)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None

------------------------------

out = team.run(
    input=final_prompt,
    session_id=session_id,
    output_schema=ChatStructuredOutput,  # ✅ Agno structured output :contentReference[oaicite:5]{index=5}
)

# When output_schema is used, `out.content` may now be a typed object.
structured = _extract_structured_output(out)

# Build reply + graph_json from structured output if present
reply = ""
graph_json = None

if structured:
    reply = str(structured.get("reply_text", "")) if isinstance(structured, dict) else str(structured)
    graph_json = structured.get("graph_json") if isinstance(structured, dict) else None
else:
    # Fallback to plain text
    reply = _extract_team_content(out)
    # Fallback extraction if graph is embedded as ```json ... ```
    graph_json = _extract_json_fence(reply)

agent_used = extract_agent_used(out)

# This is what we return to UI
structured_output = {"reply_text": reply, "graph_json": graph_json} if (reply or graph_json) else None

----------------------------

out = team.run(
    input=final_prompt,
    session_id=session_id,
    output_schema=ChatStructuredOutput,  # ✅ Agno structured output :contentReference[oaicite:5]{index=5}
)

# When output_schema is used, `out.content` may now be a typed object.
structured = _extract_structured_output(out)

# Build reply + graph_json from structured output if present
reply = ""
graph_json = None

if structured:
    reply = str(structured.get("reply_text", "")) if isinstance(structured, dict) else str(structured)
    graph_json = structured.get("graph_json") if isinstance(structured, dict) else None
else:
    # Fallback to plain text
    reply = _extract_team_content(out)
    # Fallback extraction if graph is embedded as ```json ... ```
    graph_json = _extract_json_fence(reply)

agent_used = extract_agent_used(out)

# This is what we return to UI
structured_output = {"reply_text": reply, "graph_json": graph_json} if (reply or graph_json) else None

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

----------------------


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
-----------

