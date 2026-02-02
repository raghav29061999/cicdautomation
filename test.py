# src/ui/__init__.py
"""
UI module (Streamlit)

Fully isolated from pipeline internals.
Shows only:
- TestCases.json
- TestData.json
- Gherkin (.feature files)

Entry will be wired from src/main.py later.
"""
--------------------------------------------------

# src/ui/view_models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    content: bytes


@dataclass(frozen=True)
class UiRunConfig:
    """
    data_mode:
      - "generate"  -> pipeline generates TestData.json
      - "provided"  -> user uploads JSON/XLSX; pipeline uses it
    """
    data_mode: str
    provided_testdata: Optional[UploadedFile] = None
    gherkin_max_files: int = 5  # 0 => unlimited

-------------------
# src/ui/render.py
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

import streamlit as st


def render_outputs(run_dir: Path) -> None:
    """
    Render ONLY:
      - TestCases.json
      - TestData.json
      - gherkin/*.feature
    """
    st.subheader("✅ Outputs")

    tc_path = run_dir / "TestCases.json"
    td_path = run_dir / "TestData.json"
    gherkin_dir = run_dir / "gherkin"

    col1, col2 = st.columns(2)

    with col1:
        _render_json_file(tc_path, title="TestCases.json")

    with col2:
        _render_json_file(td_path, title="TestData.json")

    st.divider()
    _render_gherkin_files(gherkin_dir)


def _render_json_file(path: Path, title: str) -> None:
    st.markdown(f"### {title}")
    if not path.exists():
        st.warning(f"{title} not found in run folder.")
        return

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        st.error(f"Failed to read {title}: {e}")
        st.text(path.read_text(encoding="utf-8"))
        return

    st.json(obj)

    st.download_button(
        label=f"⬇️ Download {title}",
        data=json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8"),
        file_name=title,
        mime="application/json",
    )


def _render_gherkin_files(gherkin_dir: Path) -> None:
    st.markdown("### Gherkin (.feature) files")

    if not gherkin_dir.exists() or not gherkin_dir.is_dir():
        st.warning("No gherkin folder found for this run.")
        return

    feature_files = sorted([p for p in gherkin_dir.glob("*.feature") if p.is_file()])
    if not feature_files:
        st.warning("No .feature files found.")
        return

    # Preview selector
    names = [p.name for p in feature_files]
    selected = st.selectbox("Preview a feature file", names)

    sel_path = gherkin_dir / selected
    st.text_area("Preview", sel_path.read_text(encoding="utf-8"), height=300)

    # Download ZIP
    zip_bytes = _zip_files(feature_files)
    st.download_button(
        label="⬇️ Download all Gherkin as ZIP",
        data=zip_bytes,
        file_name="gherkin_features.zip",
        mime="application/zip",
    )


def _zip_files(paths: List[Path]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            z.writestr(p.name, p.read_text(encoding="utf-8"))
    return buf.getvalue()

-------------------
# src/ui/app.py
from __future__ import annotations

import os
from pathlib import Path
import time

import streamlit as st
from dotenv import load_dotenv

from src.ui.view_models import UploadedFile, UiRunConfig
from src.ui.render import render_outputs

# Pipeline imports (kept minimal)
from src.pipeline.graph import build_graph
from src.utils import _read_prompt_file, get_access_token, get_llm


def run_app() -> None:
    load_dotenv()

    st.set_page_config(page_title="Agentic Test Design", layout="wide")
    st.title("🧠 Agentic Test Design Pipeline")
    st.caption("Upload a user story → generate TestCases, TestData, and Gherkin")

    story_file = st.file_uploader("Upload User Story (.txt)", type=["txt"])
    if not story_file:
        st.info("Upload a .txt user story to begin.")
        return

    story_text = story_file.read().decode("utf-8", errors="replace")
    st.subheader("📄 User Story Preview")
    st.text_area("User Story", story_text, height=200)

    st.divider()
    st.subheader("⚙️ Run Options")

    data_mode = st.radio(
        "Test Data Mode",
        options=["generate", "provided"],
        format_func=lambda x: "Generate test data" if x == "generate" else "Upload test data (JSON/XLSX)",
        horizontal=True,
    )

    provided_data_file = None
    if data_mode == "provided":
        uploaded = st.file_uploader("Upload Test Data (.json or .xlsx)", type=["json", "xlsx"])
        if uploaded:
            provided_data_file = UploadedFile(filename=uploaded.name, content=uploaded.read())
        else:
            st.warning("Upload a Test Data file or switch mode to Generate.")
            return

    gherkin_max_files = st.number_input(
        "Max Gherkin files (0 = unlimited)",
        min_value=0,
        max_value=200,
        value=int(os.getenv("GHERKIN_MAX_FILES", "5")),
        step=1,
    )

    config = UiRunConfig(
        data_mode=data_mode,
        provided_testdata=provided_data_file,
        gherkin_max_files=int(gherkin_max_files),
    )

    st.divider()

    if st.button("🚀 Run Pipeline", type="primary"):
        with st.spinner("Running pipeline..."):
            run_dir = _run_pipeline(story_text, config)

        st.success(f"Run completed: {run_dir.name}")
        render_outputs(run_dir)


def _run_pipeline(story_text: str, cfg: UiRunConfig) -> Path:
    """
    Executes the LangGraph pipeline and returns the latest run directory path.
    """
    # Load prompts
    prompt_phase1 = _read_prompt_file(os.getenv("PROMPT_PHASE1_PATH", "./src/prompts/phase1_runtime_artifacts.txt"))
    prompt_testcases = _read_prompt_file(os.getenv("PROMPT_TESTCASES_PATH", "./src/prompts/test_case_generation.txt"))
    prompt_testdata = _read_prompt_file(os.getenv("PROMPT_TESTDATA_PATH", "./src/prompts/test_data_generation.txt"))
    prompt_gherkin = _read_prompt_file(os.getenv("PROMPT_GHERKIN_PATH", "./src/prompts/gherkin_generation.txt"))

    # LLM
    access_token = get_access_token()
    llm = get_llm(access_token)

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
        "gherkin_max_files": cfg.gherkin_max_files,

        # NEW: user test data mode (pipeline wiring comes next)
        "data_mode": cfg.data_mode,
        "provided_testdata_filename": cfg.provided_testdata.filename if cfg.provided_testdata else None,
        "provided_testdata_bytes": cfg.provided_testdata.content if cfg.provided_testdata else None,

        "warnings": [],
    }

    graph.invoke(initial_state)

    # Find latest run folder
    runtime_root = Path(os.getenv("RUNTIME_ROOT", "./runtime"))
    runs_dir = runtime_root / "runs"
    if not runs_dir.exists():
        raise RuntimeError("runtime/runs folder not found. Pipeline did not write outputs.")

    latest_run = sorted(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime)[-1]
    return latest_run
---------------

streamlit
openpyxl
python-dotenv
pydantic>=2.0
