def run_query(self, query: str) -> str:
    h = _sql_hash(query)
    preview = _sql_preview(query)

    err = validate_read_only_sql(query)
    if err:
        # AUDIT: denied
        log_error(
            f"SQL_AUDIT decision=deny tool=postgres_tools op=run_query "
            f"sql_hash={h} reason={err} preview='{preview}'"
        )
        log_debug(f"Rejected SQL full_text sql_hash={h}: {query}")
        return f"ERROR: Read-only SQL policy violation. {err}"

    # AUDIT: allowed (start)
    log_debug(
        f"SQL_AUDIT decision=allow tool=postgres_tools op=run_query "
        f"sql_hash={h} preview='{preview}'"
    )

    t0 = time.perf_counter()
    result = super().run_query(query)
    dt_ms = int((time.perf_counter() - t0) * 1000)

    # Heuristic: PostgresTools returns "Error executing query:" on DB errors
    is_error = isinstance(result, str) and result.lower().startswith("error executing query:")

    # AUDIT: finished
    if is_error:
        log_error(
            f"SQL_AUDIT decision=done tool=postgres_tools op=run_query "
            f"sql_hash={h} latency_ms={dt_ms} status=error"
        )
    else:
        log_debug(
            f"SQL_AUDIT decision=done tool=postgres_tools op=run_query "
            f"sql_hash={h} latency_ms={dt_ms} status=ok"
        )

    return result




----------------------


def inspect_query(self, query: str) -> str:
    h = _sql_hash(query)
    preview = _sql_preview(query)

    err = validate_read_only_sql(query)
    if err:
        log_error(
            f"SQL_AUDIT decision=deny tool=postgres_tools op=inspect_query "
            f"sql_hash={h} reason={err} preview='{preview}'"
        )
        log_debug(f"Rejected SQL full_text (inspect) sql_hash={h}: {query}")
        return f"ERROR: Read-only SQL policy violation. {err}"

    log_debug(
        f"SQL_AUDIT decision=allow tool=postgres_tools op=inspect_query "
        f"sql_hash={h} preview='{preview}'"
    )

    t0 = time.perf_counter()
    result = super().inspect_query(query)
    dt_ms = int((time.perf_counter() - t0) * 1000)

    is_error = isinstance(result, str) and result.lower().startswith("error executing query:")

    if is_error:
        log_error(
            f"SQL_AUDIT decision=done tool=postgres_tools op=inspect_query "
            f"sql_hash={h} latency_ms={dt_ms} status=error"
        )
    else:
        log_debug(
            f"SQL_AUDIT decision=done tool=postgres_tools op=inspect_query "
            f"sql_hash={h} latency_ms={dt_ms} status=ok"
        )

    return result








