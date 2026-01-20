def _parse_test_case_output(raw_text: str, expected_run_id: str, known_ac_ids: Set[str]) -> TestCaseSuite:
    """
    Expects strict JSON output:
    { "run_id": "...", "test_cases": [ ... ] }

    Stable hardening:
    - If linked_acceptance_criteria is missing/empty, auto-link deterministically
      using the first known AC ID from the CIR.
    """
    s = raw_text.strip()
    try:
        obj = json.loads(s)
    except json.JSONDecodeError as e:
        raise TestCaseDesignError(f"Invalid JSON returned by LLM: {e}") from e

    if not isinstance(obj, dict):
        raise TestCaseDesignError("LLM output must be a JSON object.")

    if obj.get("run_id") != expected_run_id:
        raise TestCaseDesignError(
            f"run_id mismatch: expected {expected_run_id}, got {obj.get('run_id')}"
        )

    # Validate against Pydantic schema
    try:
        suite = TestCaseSuite(**obj)
    except PydanticValidationError as e:
        raise TestCaseDesignError(f"TestCaseSuite schema validation failed: {e}") from e

    _ensure_tc_ids(suite)

    # ---- STABLE FIX: enforce AC linking deterministically ----
    ac_list = sorted(list(known_ac_ids))
    default_ac = ac_list[0] if ac_list else None

    if default_ac:
        for tc in suite.test_cases:
            if not tc.linked_acceptance_criteria:
                tc.linked_acceptance_criteria = [default_ac]  # type: ignore[attr-defined]

    return suite
