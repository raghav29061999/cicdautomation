def node_generate_test_data(state: PipelineState) -> PipelineState:
    """
    Generates TestData.json using CIR + CoverageIntent + TestCases (+ optional AmbiguityReport).
    """
    llm = state["llm"]
    artifacts = state["artifacts"]
    prompt_testdata = state["prompt_testdata"]

    cir_dict = artifacts["CanonicalUserStoryCIR.json"]
    coverage_dict = artifacts["CoverageIntent.json"]
    ambiguity_dict = artifacts.get("AmbiguityReport.json")

    test_cases_obj = state["test_cases_obj"]

    # Use your new generator
    from test_data_design.generator import TestDataGenerator
    gen = TestDataGenerator(llm)

    suite = gen.generate(
        prompt_text=prompt_testdata,
        cir=cir_dict,
        coverage=coverage_dict,
        test_cases=test_cases_obj,
        ambiguity=ambiguity_dict,
    )

    # Governance validation: must link to known AC + TC IDs
    known_ac_ids = {ac["ac_id"] for ac in cir_dict.get("functional_requirements", []) if "ac_id" in ac}
    known_tc_ids = {tc["test_case_id"] for tc in test_cases_obj.get("test_cases", []) if "test_case_id" in tc}

    from test_data_design.validator import TestDataValidator
    TestDataValidator().validate(suite, known_ac_ids=known_ac_ids, known_tc_ids=known_tc_ids)

    state["test_data_obj"] = suite.model_dump()
    return state

-----------------------


def node_write_test_data(state: PipelineState) -> PipelineState:
    """
    Writes TestData.json into runtime/runs/<run_id>/ and updates RunManifest.json inventory.
    """
    import json
    from pathlib import Path

    run_dir = Path(state["run_dir"]).resolve()
    out_path = run_dir / "TestData.json"

    obj = state["test_data_obj"]
    out_path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    # Update manifest inventory
    manifest_path = run_dir / "RunManifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            inv = manifest.get("file_inventory", [])
            if "TestData.json" not in inv:
                inv.append("TestData.json")
                manifest["file_inventory"] = sorted(inv)
                manifest_path.write_text(
                    json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        except Exception:
            pass

    return state
------------------
from pipeline.nodes import (
    node_phase1_generate,
    node_phase1_write_runtime,
    node_generate_test_cases,
    node_write_test_cases,
    node_generate_test_data,      # NEW
    node_write_test_data,         # NEW
)

...

g.add_node("generate_test_data", node_generate_test_data)
g.add_node("write_test_data", node_write_test_data)

...

g.add_edge("write_test_cases", "generate_test_data")
g.add_edge("generate_test_data", "write_test_data")
g.add_edge("write_test_data", END)
