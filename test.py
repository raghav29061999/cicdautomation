def _extract_acceptance_criteria(out: dict) -> list:
    fr = out.get("functional_requirements")

    # Case 1: already a list
    if isinstance(fr, list):
        return fr

    # Case 2: dict wrapper
    if isinstance(fr, dict):
        for key in ["acceptance_criteria", "criteria", "acs", "items"]:
            v = fr.get(key)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                # sometimes LLM returns { "AC-1": {...}, "AC-2": {...} }
                # convert dict values to list
                return list(v.values())

    # Case 3: sometimes the AC list is accidentally placed at top-level
    for key in ["acceptance_criteria", "acceptanceCriteria"]:
        v = out.get(key)
        if isinstance(v, list):
            return v

    return []
