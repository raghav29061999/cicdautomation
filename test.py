# src/main.py
from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st
from dotenv import load_dotenv

from src.pipeline.graph import build_graph
from src.utils import get_access_token, get_llm, _read_prompt_file

from src.ui.pages.about import render_about
from src.ui.pages.studio import render_studio


def _ensure_streamlit_context() -> None:
    """
    If user runs: python -m src.main
    we are NOT in a Streamlit runtime, so Streamlit UI won't render.

    Fix:
      - Relaunch this module using: python -m streamlit run <this_file>
      - Then exit current process.
    """
    # Streamlit sets these env vars when it's actually running the script.
    in_streamlit = (
        os.environ.get("STREAMLIT_SERVER_PORT") is not None
        or os.environ.get("STREAMLIT_BROWSER_GATHER_USAGE_STATS") is not None
        or os.environ.get("STREAMLIT_RUNTIME") is not None
    )

    # Another reliable check: streamlit uses a different argv pattern
    called_by_streamlit = any("streamlit" in a.lower() for a in sys.argv)

    if in_streamlit or called_by_streamlit:
        return

    # Relaunch using streamlit
    this_file = Path(__file__).resolve()

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(this_file),
        "--server.headless=true",
    ]

    # On some corporate machines, browser auto-open may fail; user can open localhost manually.
    print("Launching Streamlit UI via:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    raise SystemExit(0)


def run_pipeline(*, story_text: str, data_file: Optional[Any] = None) -> Dict[str, Any]:
    """
    Pipeline callback used by Studio page.
    Must accept keyword args: story_text and data_file.
    """
    load_dotenv()

    runtime_root = os.getenv("RUNTIME_ROOT", "./runtime")
    Path(runtime_root).mkdir(parents=True, exist_ok=True)

    # Prompts (ensure these exist)
    prompt_phase1 = _read_prompt_file(os.getenv("PROMPT_PHASE1_PATH", "./src/prompts/phase1_runtime_artifacts.txt"))
    prompt_testcases = _read_prompt_file(os.getenv("PROMPT_TESTCASES_PATH", "./src/prompts/test_case_generation.txt"))
    prompt_testdata = _read_prompt_file(os.getenv("PROMPT_TESTDATA_PATH", "./src/prompts/test_data_generation.txt"))
    prompt_gherkin = _read_prompt_file(os.getenv("PROMPT_GHERKIN_PATH", "./src/prompts/gherkin_generation.txt"))

    token = get_access_token()
    llm = get_llm(token)

    data_mode = "provided" if data_file is not None else "generate"

    # Convert UploadedFile -> bytes + name (avoid passing file object around)
    user_test_data_bytes = None
    user_test_data_name = None
    if data_file is not None:
        try:
            user_test_data_bytes = data_file.getvalue()
            user_test_data_name = getattr(data_file, "name", "uploaded_data")
        except Exception:
            # leave as None; ingest node should handle or error clearly
            pass

    graph = build_graph().compile()

    initial_state: Dict[str, Any] = {
        "story_text": story_text,
        "runtime_root": runtime_root,
        "llm": llm,

        # prompts
        "prompt_phase1": prompt_phase1,
        "prompt_testcases": prompt_testcases,
        "prompt_testdata": prompt_testdata,
        "prompt_gherkin": prompt_gherkin,

        # branching
        "data_mode": data_mode,
        "user_test_data_bytes": user_test_data_bytes,
        "user_test_data_name": user_test_data_name,

        "warnings": [],
    }

    final_state = graph.invoke(initial_state)

    return {
        "run_id": final_state.get("run_id"),
        "run_dir": final_state.get("run_dir"),
        "warnings": final_state.get("warnings", []),
        "test_cases_path": final_state.get("test_cases_path"),
        "test_data_path": final_state.get("test_data_path"),
        "gherkin_dir": final_state.get("gherkin_dir"),
    }


def main() -> None:
    # ✅ If you ran python -m src.main, this will relaunch as Streamlit and exit.
    _ensure_streamlit_context()

    # Now we are inside streamlit runtime -> render UI
    st.set_page_config(page_title="Agentic Test Designer", layout="wide")

    if "ui_page" not in st.session_state:
        st.session_state.ui_page = "about"

    def go_studio() -> None:
        st.session_state.ui_page = "studio"
        st.rerun()

    with st.sidebar:
        st.title("Agentic Test Designer")
        choice = st.radio("Navigate", ["About", "Studio"], index=0 if st.session_state.ui_page == "about" else 1)
        st.session_state.ui_page = "about" if choice == "About" else "studio"
        st.divider()
        st.caption("Upload a story, optionally upload test data, then Run.")

    if st.session_state.ui_page == "about":
        render_about(on_cta_click=go_studio)
    else:
        render_studio(run_pipeline_callback=run_pipeline)


if __name__ == "__main__":
    main()
