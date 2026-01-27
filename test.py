def node_generate_gherkin(state: PipelineState) -> PipelineState:
    """
    Generate Gherkin .feature files from CIR + TestCases + TestData.
    Applies a stable limiter: default 5; if 0 then unlimited; if N then cap at N.
    """
    from gherkin_design.generator import GherkinGenerator
    from gherkin_design.gherkin_schema import GherkinGenerationControl

    llm = state["llm"]
    prompt = state["prompt_gherkin"]

    artifacts = state["artifacts"]
    cir = artifacts["CanonicalUserStoryCIR.json"]

    test_cases = state["test_cases_obj"]
    test_data = state["test_data_obj"]

    max_files = state.get("gherkin_max_files", 5)
    if max_files is None:
        max_files = 5
    if not isinstance(max_files, int) or max_files < 0:
        max_files = 5

    # Control object for prompt + strategy
    if max_files == 0:
        control = GherkinGenerationControl(strategy="max_coverage", max_scenarios=None)
    else:
        control = GherkinGenerationControl(strategy="limit", max_scenarios=max_files)

    gen = GherkinGenerator(llm)
    files = gen.generate(
        prompt_text=prompt,
        cir=cir,
        test_cases=test_cases,
        test_data=test_data,
        control=control,
    )

    # HARD ENFORCEMENT (permanent guardrail)
    if max_files != 0:
        files = files[:max_files]

    # store as serializable objects in state
    state["gherkin_files"] = [{"filename": f.filename, "content": f.content} for f in files]
    return state


def node_write_gherkin(state: PipelineState) -> PipelineState:
    """
    Write generated .feature files under runtime/runs/<run_id>/gherkin/
    and update RunManifest.json inventory.
    """
    import json
    from pathlib import Path

    from gherkin_design.gherkin_schema import GherkinFeatureFile
    from gherkin_design.writer import write_gherkin_files

    run_dir = Path(state["run_dir"]).resolve()
    files_in_state = state.get("gherkin_files", [])

    feature_files = [GherkinFeatureFile(filename=f["filename"], content=f["content"]) for f in files_in_state]
    gherkin_dir = write_gherkin_files(run_dir, feature_files)

    # Update manifest inventory (add folder + filenames)
    manifest_path = run_dir / "RunManifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            inv = set(manifest.get("file_inventory", []))

            inv.add("gherkin/")  # logical marker
            for f in feature_files:
                inv.add(f"gherkin/{f.filename}")

            manifest["file_inventory"] = sorted(inv)
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass

    # optionally expose in state
    state["gherkin_dir"] = str(gherkin_dir)
    return state


---------------------

from pipeline.nodes import (
    # existing...
    node_generate_test_data,
    node_write_test_data,
    node_generate_gherkin,     # NEW
    node_write_gherkin,        # NEW
)

# add nodes
g.add_node("generate_gherkin", node_generate_gherkin)
g.add_node("write_gherkin", node_write_gherkin)

# edges (after writing test data)
g.add_edge("write_test_data", "generate_gherkin")
g.add_edge("generate_gherkin", "write_gherkin")
g.add_edge("write_gherkin", END)


