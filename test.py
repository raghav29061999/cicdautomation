def _call_agent(agent_obj: Any, message: str, session_id: str, metadata: Dict[str, Any]) -> str:
    """
    Calls agent with flexible signatures:
    - run(input=...)
    - run(message=...)
    - run(...)
    - respond(message)
    - __call__(...)
    """
    # 1) run() with input kw
    if hasattr(agent_obj, "run") and callable(agent_obj.run):
        try:
            out = agent_obj.run(input=message, session_id=session_id, metadata=metadata)
            return out if isinstance(out, str) else str(out)
        except TypeError:
            pass

        # 2) run() with message kw
        try:
            out = agent_obj.run(message=message, session_id=session_id, metadata=metadata)
            return out if isinstance(out, str) else str(out)
        except TypeError:
            pass

        # 3) run() positional only
        out = agent_obj.run(message)
        return out if isinstance(out, str) else str(out)

    # 4) respond(message)
    if hasattr(agent_obj, "respond") and callable(agent_obj.respond):
        out = agent_obj.respond(message)
        return out if isinstance(out, str) else str(out)

    # 5) callable agent
    if callable(agent_obj):
        try:
            out = agent_obj(input=message, session_id=session_id, metadata=metadata)
            return out if isinstance(out, str) else str(out)
        except TypeError:
            out = agent_obj(message)
            return out if isinstance(out, str) else str(out)

    raise TypeError(f"Agent {type(agent_obj).__name__} has no callable interface (run/respond/__call__).")
