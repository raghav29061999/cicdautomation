test_cases = obj.get("test_cases", [])

for tc in test_cases:
    linked = tc.get("linked_acceptance_criteria")

    # If missing or empty, auto-attach deterministically
    if not linked:
        # Rule: attach the FIRST AC (most conservative, traceable)
        tc["linked_acceptance_criteria"] = [known_ac_ids[0]]
        tc.setdefault("notes", []).append(
            "Auto-linked to primary acceptance criteria due to missing linkage in generation."
        )
