from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


def node_execute_gherkin(state: dict) -> dict:
    """
    Execute generated Gherkin files using Playwright executor.

    Expected inputs in state:
      - run_id: str
      - run_dir: str
      - optional base_url_override: str (defaults to https://www.amazon.com)
      - optional execution_limit_files: int (0 => all)

    Produces (expected by UI):
      runtime/<run_id>/execution/report.json
      runtime/<run_id>/execution/report.pdf
    """

    run_id = (state.get("run_id") or "UNKNOWN").strip()
    run_dir = state.get("run_dir")
    if not run_dir:
        raise RuntimeError("node_execute_gherkin: run_dir missing in state.")

    run_dir_p = Path(run_dir)
    if not run_dir_p.exists():
        raise RuntimeError(f"node_execute_gherkin: run_dir not found: {run_dir_p}")

    # ----------------------------
    # Locate gherkin folder
    # ----------------------------
    candidates = [
        run_dir_p / "gherkin",
        run_dir_p / "features",
        run_dir_p / "gherkin_files",
        run_dir_p,  # last resort
    ]

    gherkin_dir: Optional[Path] = None
    for c in candidates:
        if c.exists() and any(c.glob("*.feature")):
            gherkin_dir = c
            break

    if gherkin_dir is None:
        raise RuntimeError(
            f"node_execute_gherkin: No .feature files found under {run_dir_p}. "
            f"Checked: {[str(x) for x in candidates]}"
        )

    execution_dir = run_dir_p / "execution"
    execution_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------
    # Config
    # ----------------------------
    base_url_override = (state.get("base_url_override") or "https://www.amazon.com").strip()
    limit_files = int(state.get("execution_limit_files") or 0)  # 0 => all

    # Try to import your config + runner in a tolerant way
    try:
        from src.executor.config import ExecutorConfig  # type: ignore
    except Exception:
        ExecutorConfig = None  # type: ignore

    # Config as dict is most compatible (works even if pydantic/dataclass mismatch)
    cfg_dict: Dict[str, Any] = {
        "run_id": run_id,
        "headless": True,
        "browser": "chromium",
        "slow_mo_ms": 0,
        "stop_on_first_failure": False,
        "base_url": base_url_override,
        "limit_files": limit_files,
    }

    cfg_obj: Any = None
    if ExecutorConfig is not None:
        try:
            cfg_obj = ExecutorConfig(
                headless=True,
                browser="chromium",
                slow_mo_ms=0,
                stop_on_first_failure=False,
            )
        except Exception:
            cfg_obj = None

    # ----------------------------
    # Call executor (supports multiple APIs)
    # ----------------------------
    report: Any = None
    last_err: Optional[Exception] = None

    # 1) Preferred: run_features(...)
    try:
        from src.executor.runner import run_features  # type: ignore

        report = run_features(
            run_id=run_id,
            run_dir=run_dir_p,
            gherkin_dir=gherkin_dir,
            config=(cfg_obj or cfg_dict),
            limit_files=limit_files,
            base_url_override=base_url_override,
        )
    except Exception as e:
        last_err = e
        report = None

    # 2) Alternate: run_gherkin_folder(gherkin_dir=..., run_dir=..., config=...)
    if report is None:
        try:
            from src.executor.playwright_runner import run_gherkin_folder  # type: ignore

            report = run_gherkin_folder(
                gherkin_dir=str(gherkin_dir),
                run_dir=str(run_dir_p),
                config=(cfg_obj or cfg_dict),
            )
        except Exception as e:
            last_err = e
            report = None

    # 3) Alternate: run_features_folder(...)
    if report is None:
        try:
            from src.executor.playwright_runner import run_features_folder  # type: ignore

            report = run_features_folder(
                gherkin_dir=str(gherkin_dir),
                run_dir=str(run_dir_p),
                config=(cfg_obj or cfg_dict),
            )
        except Exception as e:
            last_err = e
            report = None

    # 4) Alternate: run_scenarios(...) or run_scenario(...)
    # (Only if your executor expects parsed scenarios; if it expects folder, this won't help)
    if report is None:
        try:
            from src.executor.playwright_runner import run_scenarios as _run_scenarios  # type: ignore
            # if your runner actually supports folder execution it should have worked above.
            # This path is here only to fail with a clearer error.
            raise RuntimeError(
                "Executor exposes run_scenarios but node_execute_gherkin is folder-based. "
                "Expose run_gherkin_folder/run_features_folder or use src.executor.runner.run_features."
            )
        except Exception as e:
            last_err = e
            report = None

    if report is None:
        raise RuntimeError(
            "node_execute_gherkin: Executor call failed. "
            f"Last error: {type(last_err).__name__}: {last_err}"
        )

    # ----------------------------
    # Normalize report output to state for UI
    # ----------------------------
    report_json = execution_dir / "report.json"
    report_pdf = execution_dir / "report.pdf"

    # Some implementations return a pydantic/dataclass with to_dict, some return dict
    summary: Dict[str, Any] = {}
    try:
        if hasattr(report, "to_dict") and callable(report.to_dict):
            d = report.to_dict()
            summary = (d or {}).get("summary", {}) if isinstance(d, dict) else {}
        elif isinstance(report, dict):
            summary = report.get("summary", {}) if isinstance(report.get("summary", {}), dict) else {}
        else:
            # unknown object, just stringify
            summary = {"note": "report object returned (non-dict)", "repr": repr(report)}
    except Exception:
        summary = {"note": "Unable to extract summary from report"}

    # If your executor wrote different names, UI can still use these "expected" paths:
    state["execution_report_summary"] = summary
    state["execution_report_json_path"] = str(report_json)
    state["execution_report_pdf_path"] = str(report_pdf)
    state["execution_dir"] = str(execution_dir)

    return state
