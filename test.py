# src/main.py
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def launch_ui():
    """
    Launch Streamlit UI.
    """
    ui_app = Path(__file__).parent / "ui" / "app.py"

    if not ui_app.exists():
        raise RuntimeError("UI entrypoint not found at src/ui/app.py")

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(ui_app),
    ]
    subprocess.run(cmd, check=True)


def run_cli(story_path: str):
    """
    Run pipeline in CLI mode (no UI).
    """
    from src.ingestion.story_loader import load_user_stories
    from src.pipeline.graph import build_graph
    from src.utils.llm import get_llm, get_access_token
    from dotenv import load_dotenv

    load_dotenv()

    stories = load_user_stories(Path(story_path).parent)
    if not stories:
        raise SystemExit(f"No story found in {story_path}")

    story = next(s for s in stories if s.filename == Path(story_path).name)

    llm = get_llm(get_access_token())

    graph = build_graph().compile()

    initial_state = {
        "story_id": story.story_id,
        "story_filename": story.filename,
        "story_text": story.raw_text,
        "llm": llm,
        "data_mode": "generate",  # or "provided"
        "warnings": [],
    }

    final_state = graph.invoke(initial_state)

    print("\nPipeline completed successfully")
    print("Run ID:", final_state.get("run_id"))
    print("Output dir:", final_state.get("run_dir"))


def main():
    parser = argparse.ArgumentParser(description="Agentic Test Generator")
    parser.add_argument(
        "--story",
        type=str,
        help="Run pipeline in CLI mode with a user story file",
    )

    args = parser.parse_args()

    if args.story:
        run_cli(args.story)
    else:
        launch_ui()


if __name__ == "__main__":
    main()


--------


def launch_ui():
    """
    Launch Streamlit UI (safe for python -m src.main).
    """
    ui_app = Path(__file__).parent / "ui" / "app.py"

    if not ui_app.exists():
        raise RuntimeError("UI entrypoint not found at src/ui/app.py")

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(ui_app),
        "--server.port=8501",
        "--server.address=localhost",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]

    print("Launching Streamlit UI at http://localhost:8501")
    subprocess.Popen(cmd)   # ✅ non-blocking
    raise SystemExit(0)     # ✅ prevent relaunch loop





