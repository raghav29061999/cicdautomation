def _resolve_request_inputs(
    req: ChatRequest,
    request_id: str,
    session_id: str,
    metadata: Dict[str, Any],
    store: InMemoryEventStore,
) -> tuple[str | None, str | None]:
    table_name = (req.table_name or "").strip() if req.table_name else None
    user_query = (req.user_query or "").strip() if req.user_query else None

    if table_name and user_query:
        return table_name, user_query

    if req.message:
        store.add(
            type="chat_request_legacy",
            session_id=session_id,
            payload={
                "message": req.message.strip(),
                "metadata": metadata,
                "request_id": request_id,
            },
        )
        raise HTTPException(
            status_code=400,
            detail="Legacy request detected. Please use: table_name + user_query (+ session_id).",
        )

    raise HTTPException(status_code=400, detail="Provide table_name and user_query")

-------------------------------------------------------------------------------------------------------

def _resolve_selected_table(
    store: InMemoryEventStore,
    session_id: str,
    table_name: str | None,
) -> str | None:
    if table_name:
        store.set_session_value(session_id, "selected_table", table_name)
    return store.get_session_value(session_id, "selected_table", None)


------------------------------------------------------------------------------------------------

def _run_team_with_fallback(
    *,
    team: Team,
    final_prompt: str,
    session_id: str,
    request_id: str,
    selected_table: str,
    user_query: str,
    store: InMemoryEventStore,
) -> tuple[str, str, Dict[str, Any] | None]:
    try:
        log_debug(f"CHAT team_run_start request_id={request_id} session_id={session_id}")
        out = team.run(input=final_prompt, session_id=session_id)

        raw_text = _extract_text_from_any(out)
        clean_text, graph_json_str = _extract_graph_from_fence(raw_text)

        reply = _extract_team_content(out) or clean_text or raw_text
        agent_used = extract_agent_used(out)

        structured_output = None
        if graph_json_str and graph_json_str.strip():
            structured_output = {"graph_json": graph_json_str}

        return reply, agent_used, structured_output

    except Exception as e:
        log_error(f"CHAT team_run_failed request_id={request_id} session_id={session_id} error={e}")
        store.add(
            type="chat_error",
            session_id=session_id,
            payload={
                "request_id": request_id,
                "error": str(e),
                "table_name": selected_table,
                "user_query": user_query,
            },
        )

        fallback = _fallback_member(team)
        if fallback is None:
            return "System is temporarily unable to process your request. Please try again.", "none", None

        log_debug(
            f"CHAT fallback_start request_id={request_id} session_id={session_id} fallback_member=first_member"
        )

        try:
            reply = _call_member(fallback, final_prompt, session_id=session_id)
            return reply, "fallback_member_0", None
        except Exception as e2:
            log_error(
                f"CHAT fallback_failed request_id={request_id} session_id={session_id} error={e2}"
            )
            return "System is temporarily unable to process your request. Please try again.", "none", None

---------------------------------------------------------------------------------------------------------------

def _build_chat_response(
    *,
    request_id: str,
    session_id: str,
    selected_table: str,
    reply: str,
    agent_used: str,
    structured_output: Dict[str, Any] | None,
    dt_ms: int,
    store: InMemoryEventStore,
) -> ChatResponse:
    final_reply = reply or "No response generated. Please rephrase your question and try again."

    log_debug(
        f"CHAT request_done request_id={request_id} session_id={session_id} "
        f"agent_used={agent_used} latency_ms={dt_ms}"
    )

    store.add(
        type="chat_response",
        session_id=session_id,
        payload={
            "request_id": request_id,
            "agent_used": agent_used,
            "reply_preview": final_reply[:200],
            "table_name": selected_table,
            "latency_ms": dt_ms,
            "structured_output": structured_output,
        },
    )

    return ChatResponse(
        session_id=session_id,
        agent_used=agent_used,
        reply=final_reply,
        structured_output=structured_output,
        raw={
            "request_id": request_id,
            "selected_table": selected_table,
        },
    )

----------------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    request: Request,
    team: Team = Depends(get_team),
    store: InMemoryEventStore = Depends(get_store),
    user=Depends(get_current_user),
) -> ChatResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    session_id = req.session_id or "default"
    metadata: Dict[str, Any] = req.metadata or {}

    rate_limit(user["user_id"])

    table_name, user_query = _resolve_request_inputs(
        req=req,
        request_id=request_id,
        session_id=session_id,
        metadata=metadata,
        store=store,
    )

    selected_table = _resolve_selected_table(store, session_id, table_name)

    if not selected_table:
        guidance = (
            "No table is selected for this session. Please send a table_name.\n"
            "Example: table_name=public.orders, user_query='show top 5 orders'"
        )
        store.add(
            type="chat_response",
            session_id=session_id,
            payload={"agent_used": "none", "reply": guidance},
        )
        return ChatResponse(
            session_id=session_id,
            agent_used="none",
            reply=guidance,
            structured_output=None,
            raw={},
        )

    final_prompt = _inject_context(user_query, selected_table)

    log_debug(
        f"CHAT request_start request_id={request_id} session_id={session_id} "
        f"table={selected_table} user_query_preview='{user_query[:120]}'"
    )

    store.add(
        type="chat_request",
        session_id=session_id,
        payload={
            "request_id": request_id,
            "table_name": selected_table,
            "user_query": user_query,
            "metadata": metadata,
        },
    )

    t0 = time.perf_counter()

    reply, agent_used, structured_output = _run_team_with_fallback(
        team=team,
        final_prompt=final_prompt,
        session_id=session_id,
        request_id=request_id,
        selected_table=selected_table,
        user_query=user_query,
        store=store,
    )

    dt_ms = int((time.perf_counter() - t0) * 1000)

    return _build_chat_response(
        request_id=request_id,
        session_id=session_id,
        selected_table=selected_table,
        reply=reply,
        agent_used=agent_used,
        structured_output=structured_output,
        dt_ms=dt_ms,
        store=store,
    )

-------------------------------------------------------------------



refactor: reduce chat endpoint cognitive complexity by extracting helper flows
