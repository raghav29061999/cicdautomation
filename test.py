### pipeline/state.py
data_mode: str  # "generate" | "provided"

provided_testdata_filename: str | None
provided_testdata_bytes: bytes | None

# outputs
test_data_obj: dict
test_cases_obj: dict
gherkin_files: list


###pipeline/nodes.py
def node_ingest_user_test_data(state: PipelineState) -> PipelineState:
    from user_data.parser import parse_user_testdata
    from user_data.normalizer import normalize_user_testdata
    from user_data.validator import validate_user_testdata

    raw = parse_user_testdata(
        filename=state.get("provided_testdata_filename"),
        content=state.get("provided_testdata_bytes"),
    )

    normalized = normalize_user_testdata(raw, run_id=state["run_id"])
    validate_user_testdata(normalized)

    state["test_data_obj"] = normalized
    return state


####pipeline/graph.py
phase1 → write_runtime
      → (generate_test_data OR ingest_user_test_data)
      → write_test_data
      → generate_test_cases (now grounded by TestData)
      → write_test_cases
      → generate_gherkin
      → write_gherkin


