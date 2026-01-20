```python
def normalize_cir_dict(cir_dict: dict) -> dict:
    """
    Normalize Phase-1 CanonicalUserStoryCIR.json (LLM/prompt output)
    into the internal Pydantic schema shape expected by contracts/cir_schema.py.

    Why this exists:
    - LLM outputs vary (keys, nesting, list vs string)
    - We keep internal contracts strict and stable
    - This function is the single compatibility adapter layer

    What it guarantees (stable invariants):
    - story_metadata has story_id, story_points, owners (list)
    - functional_requirements is a LIST of AC objects (not wrapped)
    - each AC has a deterministic ac_id (AC-1, AC-2, ...) if missing
    - AC notes / traceability_tags are LIST[str]
    - nfrs[*].testability_notes is LIST[str]
    - state_and_url_requirements is mapped to state_and_external_persistence
    """
    import json

    out = dict(cir_dict or {})

    # ----------------------------
    # story_metadata mapping
    # ----------------------------
    sm = dict(out.get("story_metadata", {}) or {})

    # story_id
    if "story_id" not in sm or not str(sm.get("story_id", "")).strip():
        sm["story_id"] = sm.get("id_if_any") or sm.get("id") or "UNKNOWN"

    # story_points (schema) from points (prompt)
    if "story_points" not in sm and "points" in sm:
        sm["story_points"] = sm["points"]

    # owners list
    if "owners" not in sm:
        if "owner" in sm and sm["owner"]:
            sm["owners"] = [str(sm["owner"])]
        else:
            sm["owners"] = []

    # remove prompt-only keys that strict schema may forbid
    sm.pop("id_if_any", None)
    sm.pop("points", None)
    sm.pop("owner", None)

    out["story_metadata"] = sm

    # ----------------------------
    # functional_requirements extraction (robust)
    # ----------------------------
    def _extract_acceptance_criteria(obj: dict) -> list:
        fr = obj.get("functional_requirements")

        # Case 1: already a list
        if isinstance(fr, list):
            return fr

        # Case 2: wrapper dict
        if isinstance(fr, dict):
            for key in ("acceptance_criteria", "criteria", "acs", "items"):
                v = fr.get(key)
                if isinstance(v, list):
                    return v
                if isinstance(v, dict):
                    # Sometimes LLM emits {"AC-1": {...}, "AC-2": {...}}
                    return list(v.values())

        # Case 3: top-level fallback keys
        for key in ("acceptance_criteria", "acceptanceCriteria"):
            v = obj.get(key)
            if isinstance(v, list):
                return v

        return []

    out["functional_requirements"] = _extract_acceptance_criteria(out)

    # ----------------------------
    # Normalize each AC object:
    # - ensure ac_id exists deterministically
    # - notes and traceability_tags are List[str]
    # ----------------------------
    fr_list = out.get("functional_requirements") or []
    fixed_fr: list = []

    if isinstance(fr_list, list):
        for idx, ac in enumerate(fr_list, start=1):
            if not isinstance(ac, dict):
                continue
            ac2 = dict(ac)

            # Ensure ac_id exists
            ac_id = ac2.get("ac_id")
            if not isinstance(ac_id, str) or not ac_id.strip():
                # allow alternate keys
                alt = ac2.get("id") or ac2.get("acId") or ac2.get("acceptance_criteria_id")
                if isinstance(alt, str) and alt.strip():
                    ac2["ac_id"] = alt.strip()
                else:
                    ac2["ac_id"] = f"AC-{idx}"

            # notes -> List[str]
            n = ac2.get("notes")
            if isinstance(n, str):
                n_str = n.strip()
                ac2["notes"] = [] if n_str == "" else [n_str]
            elif n is None:
                ac2["notes"] = []
            elif isinstance(n, list):
                ac2["notes"] = [str(x).strip() for x in n if str(x).strip()]
            else:
                ac2["notes"] = [str(n).strip()] if str(n).strip() else []

            # traceability_tags -> List[str]
            tt = ac2.get("traceability_tags")
            if isinstance(tt, str):
                tt_str = tt.strip()
                ac2["traceability_tags"] = [] if tt_str == "" else [tt_str]
            elif tt is None:
                ac2["traceability_tags"] = []
            elif isinstance(tt, list):
                ac2["traceability_tags"] = [str(x).strip() for x in tt if str(x).strip()]
            else:
                ac2["traceability_tags"] = [str(tt).strip()] if str(tt).strip() else []

            # common coercions: preconditions/triggers/expected_outcome may appear as strings
            for k in ("preconditions", "triggers"):
                v = ac2.get(k)
                if isinstance(v, str):
                    v_str = v.strip()
                    ac2[k] = [] if v_str == "" else [v_str]
                elif v is None:
                    ac2[k] = []
                elif isinstance(v, list):
                    ac2[k] = [str(x).strip() for x in v if str(x).strip()]
                else:
                    ac2[k] = [str(v).strip()] if str(v).strip() else []

            # expected_outcome should generally be a string; if list/dict, stringify deterministically
            eo = ac2.get("expected_outcome")
            if isinstance(eo, list) or isinstance(eo, dict):
                ac2["expected_outcome"] = json.dumps(eo, ensure_ascii=False, sort_keys=True)
            elif eo is None:
                ac2["expected_outcome"] = "TBD"

            fixed_fr.append(ac2)

    out["functional_requirements"] = fixed_fr

    # ----------------------------
    # nfrs normalization: testability_notes -> List[str]
    # ----------------------------
    nfrs = out.get("nfrs") or []
    fixed_nfrs: list = []
    if isinstance(nfrs, list):
        for n in nfrs:
            if not isinstance(n, dict):
                continue
            n2 = dict(n)
            tn = n2.get("testability_notes")
            if isinstance(tn, str):
                tn_str = tn.strip()
                n2["testability_notes"] = [] if tn_str == "" else [tn_str]
            elif tn is None:
                n2["testability_notes"] = []
            elif isinstance(tn, list):
                n2["testability_notes"] = [str(x).strip() for x in tn if str(x).strip()]
            else:
                n2["testability_notes"] = [str(tn).strip()] if str(tn).strip() else []
            fixed_nfrs.append(n2)
    out["nfrs"] = fixed_nfrs

    # ----------------------------
    # state/url requirements mapping
    # prompt: state_and_url_requirements -> schema: state_and_external_persistence
    # ----------------------------
    if "state_and_url_requirements" in out and "state_and_external_persistence" not in out:
        sur = out.get("state_and_url_requirements") or {}
        out["state_and_external_persistence"] = {
            "externalized_state_required": bool(sur.get("url_parameterization_required", False)),
            "mechanism": "url_parameters",
            "rules": sur.get("url_rules") or [],
        }
        out.pop("state_and_url_requirements", None)

    # ----------------------------
    # Final cleanup of known prompt-only stray keys
    # ----------------------------
    out.pop("id_if_any", None)

    return out
```
