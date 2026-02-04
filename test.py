def node_execute_gherkin(state: dict) -> dict:
    run_id = (state.get("run_id") or "UNKNOWN").strip()
    run_dir = state.get("run_dir")
    if not run_dir:
        raise RuntimeError("node_execute_gherkin: run_dir missing in state.")

    run_dir_p = Path(run_dir)
    if not run_dir_p.exists():
        raise RuntimeError(f"node_execute_gherkin: run_dir not found: {run_dir_p}")

    # Find gherkin folder
    candidates = [run_dir_p / "gherkin", run_dir_p / "features", run_dir_p / "gherkin_files", run_dir_p]
    gherkin_dir: Optional[Path] = None
    for c in candidates:
        if c.exists() and any(c.glob("*.feature")):
            gherkin_dir = c
            break
    if gherkin_dir is None:
        raise RuntimeError(f"node_execute_gherkin: No .feature files found under {run_dir_p}")

    from src.executor.config import ExecutorConfig
    from src.executor.runner import run_features

    base_url_override = (state.get("base_url_override") or "https://www.amazon.com").replace(" ", "").strip()
    limit_files = int(state.get("execution_limit_files") or 0)

    cfg = ExecutorConfig(headless=True)

    report = run_features(
        run_id=run_id,
        run_dir=run_dir_p,
        gherkin_dir=gherkin_dir,
        config=cfg,
        limit_files=limit_files,
        base_url_override=base_url_override,
    )

    execution_dir = run_dir_p / "execution"
    state["execution_report_summary"] = report.to_dict().get("summary", {})
    state["execution_report_json_path"] = str(execution_dir / "report.json")
    state["execution_report_pdf_path"] = str(execution_dir / "report.pdf")
    state["execution_dir"] = str(execution_dir)
    return state
