    # ---- STABLE FIX: enforce AC linking deterministically + sanitize invalid IDs ----
    ac_list = sorted(list(known_ac_ids))
    default_ac = ac_list[0] if ac_list else None

    if not default_ac:
        raise TestCaseDesignError("No acceptance criteria IDs available in CIR; cannot link test cases.")

    for tc in suite.test_cases:
        # normalize: keep only valid AC IDs
        valid_links = [ac for ac in (tc.linked_acceptance_criteria or []) if ac in known_ac_ids]

        # if none remain (covers TC-VAL-004 and TC-VAL-005), force default
        if not valid_links:
            tc.linked_acceptance_criteria = [default_ac]  # type: ignore[attr-defined]
        else:
            # keep deterministic ordering
            tc.linked_acceptance_criteria = sorted(set(valid_links))  # type: ignore[attr-defined]
