def validate_test_case_suite(suite, known_acceptance_criteria_ids):
    """
    Validate TestCases.json structure and governance rules.

    Accepts:
    - dict (parsed JSON)
    - OR Pydantic model with .test_cases attribute
    """

    # -------------------------
    # Normalize access
    # -------------------------
    if isinstance(suite, dict):
        test_cases = suite.get("test_cases", [])
    else:
        test_cases = getattr(suite, "test_cases", None)

    if not test_cases:
        raise ValueError("Test case suite contains no test_cases.")

    if not isinstance(test_cases, list):
        raise ValueError("test_cases must be a list.")

    # -------------------------
    # Validate each test case
    # -------------------------
    for tc in test_cases:
        _validate_single_test_case(tc, known_acceptance_criteria_ids)


def _validate_single_test_case(tc: dict, known_ac_ids: list[str]) -> None:
    """
    Validate one test case dictionary.
    """

    if not isinstance(tc, dict):
        raise ValueError("Each test case must be a JSON object.")

    # Required fields
    required_fields = [
        "test_case_id",
        "title",
        "test_type",
        "linked_acceptance_criteria",
        "steps",
        "expected_final_outcome",
    ]

    for field in required_fields:
        if field not in tc:
            raise ValueError(f"Test case missing required field: {field}")

    # AC linkage
    linked_acs = tc.get("linked_acceptance_criteria", [])
    if not linked_acs:
        raise ValueError(
            f"Test case {tc.get('test_case_id')} has no linked acceptance criteria."
        )

    for ac in linked_acs:
        if ac not in known_ac_ids:
            raise ValueError(
                f"Test case {tc.get('test_case_id')} links to unknown AC: {ac}"
            )

    # Steps
    steps = tc.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError(
            f"Test case {tc.get('test_case_id')} must contain at least one step."
        )

    for step in steps:
        if "action" not in step or "expected_result" not in step:
            raise ValueError(
                f"Each step in {tc.get('test_case_id')} must include action and expected_result."
            )
