from __future__ import annotations

import json
from pathlib import Path


def node_generate_test_data(state: dict) -> dict:
    """
    Generate TestData.json.
    Robustly finds TestCases from:
      1) state['test_cases_obj']
      2) state['test_cases']
      3) runtime run_dir / TestCases.json
    """

    # 1) Get run_dir (writer should have set it)
    run_dir = state.get("run_dir")
    if not run_dir:
        raise RuntimeError("run_dir missing in state. Phase-1 writer node must run before test data generation.")
    run_dir_path = Path(run_dir)

    # 2) Fetch TestCases object robustly
    test_cases_obj = state.get("test_cases_obj") or state.get("test_cases")

    if test_cases_obj is None:
        tc_path = run_dir_path / "TestCases.json"
        if tc_path.exists():
            test_cases_obj = json.loads(tc_path.read_text(encoding="utf-8"))

    if test_cases_obj is None:
        raise RuntimeError(
            "No TestCases available for test data generation. "
            "Expected state['test_cases_obj'] or state['test_cases'] or runtime TestCases.json. "
            "This usually means graph ordering is wrong (test_data ran before test_cases)."
        )

    # 3) Generate using your generator (keep your existing call)
    # NOTE: change these imports to match your actual module paths.
    from src.test_data_design.generator import TestDataGenerator
    from src.test_data_design.validator import validate_test_data_suite

    llm = state["llm"]
    prompt = state["prompt_testdata"]

    cir_obj = state.get("cir_obj")
    if cir_obj is None:
        cir_path = run_dir_path / "CanonicalUserStoryCIR.json"
        if not cir_path.exists():
            raise RuntimeError("CIR missing in state and not found on disk.")
        cir_obj = json.loads(cir_path.read_text(encoding="utf-8"))

    coverage_obj = state.get("coverage_obj")
    if coverage_obj is None:
        cov_path = run_dir_path / "CoverageIntent.json"
        if not cov_path.exists():
            raise RuntimeError("CoverageIntent missing in state and not found on disk.")
        coverage_obj = json.loads(cov_path.read_text(encoding="utf-8"))

    ambiguity_obj = state.get("ambiguity_obj")
    amb_path = run_dir_path / "AmbiguityReport.json"
    if ambiguity_obj is None and amb_path.exists():
        ambiguity_obj = json.loads(amb_path.read_text(encoding="utf-8"))

    # 4) Generate test data
    generator = TestDataGenerator(llm=llm, prompt=prompt)
    test_data_obj = generator.generate(
        cir_obj=cir_obj,
        coverage_obj=coverage_obj,
        test_cases_obj=test_cases_obj,
        ambiguity_obj=ambiguity_obj,
    )

    # 5) Validate and write
    validate_test_data_suite(test_data_obj)

    out_path = run_dir_path / "TestData.json"
    out_path.write_text(json.dumps(test_data_obj, indent=2, ensure_ascii=False), encoding="utf-8")

    # 6) Return updates back into state
    return {
        "test_data_obj": test_data_obj,
        "test_data_path": str(out_path),
    }


------------


graph.add_edge("phase1", "generate_test_cases")
graph.add_edge("generate_test_cases", "generate_test_data")
graph.add_edge("generate_test_data", "generate_gherkin")
