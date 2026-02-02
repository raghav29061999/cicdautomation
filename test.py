# src/main.py
"""
Entry point for the test_agentic application.

Default behavior:
  python -m src.main
    -> launches Streamlit UI (src/ui/app.py) programmatically.

Optional CLI behavior:
  python -m src.main --cli --story ./user_story/story1.txt --data-mode generate
  python -m src.main --cli --story ./user_story/story1.txt --data-mode provided --testdata ./data/TestData.xlsx

Why this file exists:
- Keep UI module separate (src/ui/*)
- Provide a single stable command for users: python -m src.main
- Avoid requiring "streamlit run ..." (often blocked in corp environments)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> None:
    args = _parse_args()

    if args.cli:
        _run_cli(args)
        return

    _run_streamlit_ui()


# ---------------------------------------------------------------------
# UI launcher
# ---------------------------------------------------------------------

def _run_streamlit_ui() -> None:
    """
    Launch Streamlit UI via the Streamlit CLI entry (programmatic).
    This is often more reliable than calling "streamlit run" directly in corp Windows setups.
    """
    try:
        from streamlit.web import cli as stcli  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Streamlit is not installed or cannot be imported. "
            "Install with: pip install streamlit"
        ) from e

    app_path = Path(__file__).parent / "ui" / "app.py"
    if not app_path.exists():
        raise RuntimeError(f"UI app not found at: {app_path}")

    # Build argv like: streamlit run <app.py> --server.headless true
    # Headless reduces browser-launch issues; user can open localhost manually.
    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.headless",
        "true",
    ]

    # Optional: allow overriding port
    port = os.getenv("STREAMLIT_PORT")
    if port:
        sys.argv += ["--server.port", str(port)]

    stcli.main()


# ---------------------------------------------------------------------
# CLI runner (fallback / automation)
# ---------------------------------------------------------------------

def _run_cli(args: argparse.Namespace) -> None:
    """
    Run the full pipeline headlessly from CLI.
    Shows where outputs are written. Useful when Streamlit is blocked.
    """
    from dotenv import load_dotenv

    from src.pipeline.graph import build_graph
    from src.utils import _read_prompt_file, get_access_token, get_llm

    load_dotenv()

    story_path = Path(args.story)
    if not story_path.exists():
        raise FileNotFoundError(f"Story file not found: {story_path}")

    story_text = story_path.read_text(encoding="utf-8", errors="replace")

    # Load prompts
    prompt_phase1 = _read_prompt_file(os.getenv("PROMPT_PHASE1_PATH", "./src/prompts/phase1_runtime_artifacts.txt"))
    prompt_testcases = _read_prompt_file(os.getenv("PROMPT_TESTCASES_PATH", "./src/prompts/test_case_generation.txt"))
    prompt_testdata = _read_prompt_file(os.getenv("PROMPT_TESTDATA_PATH", "./src/prompts/test_data_generation.txt"))
    prompt_gherkin = _read_prompt_file(os.getenv("PROMPT_GHERKIN_PATH", "./src/prompts/gherkin_generation.txt"))

    # LLM
    access_token = get_access_token()
    llm = get_llm(access_token)

    # Provided test data (optional)
    provided_filename = None
    provided_bytes = None
    if args.data_mode == "provided":
        if not args.testdata:
            raise ValueError("--testdata is required when --data-mode provided")
        td_path = Path(args.testdata)
        if not td_path.exists():
            raise FileNotFoundError(f"Test data file not found: {td_path}")
        provided_filename = td_path.name
        provided_bytes = td_path.read_bytes()

    graph = build_graph().compile()

    initial_state = {
        "story_text": story_text,
        "llm": llm,

        # prompts
        "prompt_phase1": prompt_phase1,
        "prompt_testcases": prompt_testcases,
        "prompt_testdata": prompt_testdata,
        "prompt_gherkin": prompt_gherkin,

        # gherkin limiter
        "gherkin_max_files": int(args.gherkin_max_files),

        # data mode (pipeline must support this branch)
        "data_mode": args.data_mode,
        "provided_testdata_filename": provided_filename,
        "provided_testdata_bytes": provided_bytes,

        "warnings": [],
    }

    graph.invoke(initial_state)

    runtime_root = Path(os.getenv("RUNTIME_ROOT", "./runtime"))
    runs_dir = runtime_root / "runs"
    if not runs_dir.exists():
        raise RuntimeError("runtime/runs folder not found. Pipeline did not write outputs.")

    latest_run = sorted(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime)[-1]

    print("\n✅ Pipeline run completed.")
    print(f"Run folder: {latest_run}")
    print("Outputs (UI-relevant):")
    for name in ["TestCases.json", "TestData.json"]:
        p = latest_run / name
        print(f"  - {p} {'(OK)' if p.exists() else '(missing)'}")
    gherkin_dir = latest_run / "gherkin"
    if gherkin_dir.exists():
        feats = sorted(gherkin_dir.glob("*.feature"))
        print(f"  - {gherkin_dir} ({len(feats)} .feature files)")
    else:
        print("  - gherkin/ (missing)")


# ---------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(add_help=True)

    p.add_argument(
        "--cli",
        action="store_true",
        help="Run headless pipeline instead of launching Streamlit UI.",
    )

    p.add_argument(
        "--story",
        type=str,
        default="",
        help="Path to user story .txt file (required in CLI mode).",
    )

    p.add_argument(
        "--data-mode",
        type=str,
        choices=["generate", "provided"],
        default="generate",
        help="Use generated test data or user-provided test data.",
    )

    p.add_argument(
        "--testdata",
        type=str,
        default="",
        help="Path to test data file (.json/.xlsx). Required if --data-mode provided (CLI mode).",
    )

    p.add_argument(
        "--gherkin-max-files",
        type=int,
        default=int(os.getenv("GHERKIN_MAX_FILES", "5")),
        help="Max number of gherkin feature files (0 = unlimited).",
    )

    args = p.parse_args()

    if args.cli:
        if not args.story:
            raise ValueError("--story is required when --cli is set")

    return args


if __name__ == "__main__":
    main()
