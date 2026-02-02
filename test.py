# src/main.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st
from dotenv import load_dotenv

from src.pipeline.graph import build_graph
from src.utils import get_access_token, get_llm, _read_prompt_file

from src.ui.pages.about import render_about
from src.ui.pages.studio import render_studio


def run_pipeline(*, story_text: str, data_file: Optional[Any] = None) -> Dict[str, Any]:
    """
    Pipeline callback used by the Streamlit UI.

    IMPORTANT:
    - Must accept keyword args: story_text and data_file (because studio.py calls it that way)
    - data_file is a Streamlit UploadedFile or None
    """
    load_dotenv()

    runtime_root = os.getenv("RUNTIME_ROOT", "./runtime")
    Path(runtime_root).mkdir(parents=True, exist_ok=True)

    # Prompts (ensure these paths exist)
    prompt_phase1 = _read_prompt_file(os.getenv("PROMPT_PHASE1_PATH", "./src/prompts/phase1_runtime_artifacts.txt"))
    prompt_testcases = _read_prompt_file(os.getenv("PROMPT_TESTCASES_PATH", "./src/prompts/test_case_generation.txt"))
    prompt_testdata = _read_prompt_file(os.getenv("PROMPT_TESTDATA_PATH", "./src/prompts/test_data_generation.txt"))
    prompt_gherkin = _read_prompt_file(os.getenv("PROMPT_GHERKIN_PATH", "./src/prompts/gherkin_generation.txt"))

    # LLM
    token = get_access_token()
    llm = get_llm(token)

    # Data mode
    data_mode = "provided" if data_file is not None else "generate"

    # Compile graph
    graph = build_graph().compile()

    # IMPORTANT: If your ingest node expects bytes/name, convert here
    user_test_data_bytes = None
    user_test_data_name = None
    if data_file is not None:
        try:
            user_test_data_bytes = data_file.getvalue()
            user_test_data_name = data_file.name
        except Exception:
            # leave as None; node can handle or will raise a clear error
            pass

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

        # misc
        "warnings": [],
    }

    final_state = graph.invoke(initial_state)

    # Return compact info to UI
    return {
        "run_id": final_state.get("run_id"),
        "run_dir": final_state.get("run_dir"),
        "warnings": final_state.get("warnings", []),
        "test_cases_path": final_state.get("test_cases_path"),
        "test_data_path": final_state.get("test_data_path"),
        "gherkin_dir": final_state.get("gherkin_dir"),
    }


def main() -> None:
    st.set_page_config(page_title="Agentic Test Designer", layout="wide")

    # routing state
    if "ui_page" not in st.session_state:
        st.session_state.ui_page = "about"

    def go_about() -> None:
        st.session_state.ui_page = "about"
        st.rerun()

    def go_studio() -> None:
        st.session_state.ui_page = "studio"
        st.rerun()

    # Sidebar nav
    with st.sidebar:
        st.title("Agentic Test Designer")
        choice = st.radio("Navigate", ["About", "Studio"], index=0 if st.session_state.ui_page == "about" else 1)
        st.session_state.ui_page = "about" if choice == "About" else "studio"
        st.divider()
        st.caption("Tip: Upload a story, choose optional test data, then Run.")

    # Render page
    if st.session_state.ui_page == "about":
        render_about(on_cta_click=go_studio)
    else:
        render_studio(run_pipeline_callback=run_pipeline)


if __name__ == "__main__":
    main()
