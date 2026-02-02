# src/ui/app.py
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.pipeline.graph import build_graph


# --- Small helpers -------------------------------------------------

def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _get_llm():
    """
    Keep this import local so UI loads even if env/token isn’t set until runtime.
    Works with your existing Azure pattern:
      llm = get_llm(token)
    """
    # Try both common layouts you’ve used in your project
    try:
        from src.utils.llm import get_llm, get_access_token  # type: ignore
    except Exception:
        from src.utils import get_llm, get_access_token  # type: ignore

    token = get_access_token()
    return get_llm(token)


def _run_pipeline(story_text: str, data_file):
    """
    Studio callback: runs full pipeline and returns a compact result dict.
    """
    load_dotenv()

    # Paths (keep same env override style as your main.py)
    src_root = Path(__file__).resolve().parents[1]  # .../src
    prompt_phase1_path = os.getenv(
        "PROMPT_PHASE1_PATH", str(src_root / "prompts" / "phase1_runtime_artifacts.txt")
    )
    prompt_testcases_path = os.getenv(
        "PROMPT_TESTCASES_PATH", str(src_root / "prompts" / "test_case_generation.txt")
    )
    prompt_testdata_path = os.getenv(
        "PROMPT_TESTDATA_PATH", str(src_root / "prompts" / "test_data_generation.txt")
    )
    prompt_gherkin_path = os.getenv(
        "PROMPT_GHERKIN_PATH", str(src_root / "prompts" / "gherkin_generation.txt")
    )

    prompt_phase1 = _read_text(prompt_phase1_path)
    prompt_testcases = _read_text(prompt_testcases_path)
    prompt_testdata = _read_text(prompt_testdata_path)
    prompt_gherkin = _read_text(prompt_gherkin_path) if Path(prompt_gherkin_path).exists() else ""

    llm = _get_llm()

    # Optional user test data file -> save to runtime/uploads
    runtime_root = Path(os.getenv("RUNTIME_ROOT", "./runtime"))
    uploads_dir = runtime_root / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    data_mode = "generate"
    user_test_data_path = None

    if data_file is not None:
        data_mode = "provided"
        save_path = uploads_dir / data_file.name
        save_path.write_bytes(data_file.getvalue())
        user_test_data_path = str(save_path)

    # Build + run graph
    graph = build_graph().compile()

    initial_state = {
        "story_id": "uploaded",
        "story_filename": "uploaded_story.txt",
        "story_text": story_text,

        "prompt_phase1": prompt_phase1,
        "prompt_testcases": prompt_testcases,
        "prompt_testdata": prompt_testdata,
        "prompt_gherkin": prompt_gherkin,

        "llm": llm,
        "data_mode": data_mode,

        # Pass both keys to be tolerant of node expectations
        "user_test_data_path": user_test_data_path,
        "user_test_data_filename": (data_file.name if data_file is not None else None),

        "warnings": [],
    }

    final_state = graph.invoke(initial_state)

    return {
        "run_id": final_state.get("run_id"),
        "run_dir": final_state.get("run_dir"),
        "warnings": final_state.get("warnings", []),
    }


# --- Streamlit app -------------------------------------------------

st.set_page_config(
    page_title="Agentic QA Studio",
    page_icon="🧪",
    layout="wide",
)

# shared session defaults
if "route" not in st.session_state:
    st.session_state.route = "about"  # "about" | "studio"


def _go_studio():
    st.session_state.route = "studio"
    st.rerun()


def _go_about():
    st.session_state.route = "about"
    st.rerun()


# Router
if st.session_state.route == "about":
    from src.ui.pages.about import render_about  # type: ignore
    render_about(on_cta_click=_go_studio)
else:
    from src.ui.pages.studio import render_studio  # type: ignore
    render_studio(run_pipeline_callback=_run_pipeline)
