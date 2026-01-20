def normalize_cir_dict(cir_dict: dict) -> dict:
    """
    Normalizes Phase-1 CanonicalUserStoryCIR.json (prompt format)
    into the Pydantic schema format defined in contracts/cir_schema.py.

    This is a compatibility adapter to avoid breaking the pipeline
    when prompt output keys differ from internal schema.
    """
    out = dict(cir_dict)

    # ---- story_metadata mapping ----
    sm = dict(out.get("story_metadata", {}) or {})
    # prompt uses id_if_any, schema expects story_id
    if "story_id" not in sm:
        sm["story_id"] = sm.get("id_if_any") or sm.get("id") or "UNKNOWN"
    # prompt uses points, schema expects story_points
    if "story_points" not in sm and "points" in sm:
        sm["story_points"] = sm["points"]

    # schema uses owners:list[str]
    if "owners" not in sm and "owner" in sm:
        sm["owners"] = [sm["owner"]] if sm["owner"] else []

    # cleanup prompt-only keys that schema forbids
    sm.pop("id_if_any", None)
    sm.pop("points", None)
    out["story_metadata"] = sm

    # ---- functional_requirements mapping ----
    fr = out.get("functional_requirements")
    # prompt uses {"acceptance_criteria":[...]} but schema expects List[AcceptanceCriterionCIR]
    if isinstance(fr, dict) and "acceptance_criteria" in fr:
        out["functional_requirements"] = fr["acceptance_criteria"]

    # ---- nfrs mapping ----
    nfrs = out.get("nfrs") or []
    if isinstance(nfrs, list):
        fixed_nfrs = []
        for n in nfrs:
            if not isinstance(n, dict):
                continue
            n2 = dict(n)
            # prompt sometimes emits string instead of list
            tn = n2.get("testability_notes")
            if isinstance(tn, str):
                n2["testability_notes"] = [tn]
            elif tn is None:
                n2["testability_notes"] = []
            fixed_nfrs.append(n2)
        out["nfrs"] = fixed_nfrs

    # ---- state_and_url_requirements -> state_and_external_persistence ----
    if "state_and_url_requirements" in out and "state_and_external_persistence" not in out:
        sur = out.get("state_and_url_requirements") or {}
        out["state_and_external_persistence"] = {
            "externalized_state_required": bool(sur.get("url_parameterization_required", False)),
            "mechanism": "url_parameters",
            "rules": sur.get("url_rules") or [],
        }
        out.pop("state_and_url_requirements", None)

    # Some prompt versions name this differently:
    if "state_and_url_requirements" not in out and "state_and_url_requirements" in out:
        out.pop("state_and_url_requirements", None)

    # ---- optional: remove keys that internal schema doesn't know ----
    # (keep conservative; only pop known offenders)
    out.pop("id_if_any", None)

    return out
