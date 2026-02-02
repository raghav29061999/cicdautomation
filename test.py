# src/ui/app.py
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

from src.pipeline.graph import build_graph
from src.utils import get_access_token, get_llm, _read_prompt_file


def run_app() -> None:
    st.set_page_config(page_title="Test Agentic", layout="wide")

    st.title("🧪 Test Agentic System")
    st.caption("Generate Test Cases, Test Data, and Gherkin from a User Story")

    # -------------------------
    # Inputs
    # -------------------------

    st.header("1️⃣ Upload User Story")

    story_file = st.file_uploader(
        "Upload user story (.txt)",
        type=["txt"],
        accept_multiple_files=False,
    )

    st.header("2️⃣ Test Data Mode")

    data_mode = st.radio(
        "Choose test data strategy",
        options=["Generate test data", "Use provided test data"],
        index=0,
    )

    provided_testdata = None
    if data_mode == "Use provided test data":
        provided_testdata = st.file_uploader(
            "Upload test data (.json or .xlsx)",
            type=["json", "xlsx"],
            accept_multiple_files=False,
        )

    st.header("3️⃣ Gherkin Generation Control")

    max_gherkin = st.number_input(
        "Max Gherkin scenarios (0 = all)",
        min_value=0,
        max_value=50,
        value=5,
        step=1,
    )

    # -------------------------
    # Run pipeline
    # -------------------------

    st.divider()
    run_clicked = st.button("🚀 Generate Artifacts", type="primary")

    if not run_clicked:
        return

    if not story_file:
        st.error("Please upload a user story file.")
        return

    if data_mode == "Use provided test data" and not provided_testdata:
        st.error("Please upload test data or switch to auto-generation.")
        return

    with st.spinner("Running pipeline..."):
        story_text = story_file.read().decode("utf-8", errors="replace")

        # Load prompts
        prompt_phase1 = _read_prompt_file("./src/prompts/phase1_runtime_artifacts.txt")
        prompt_testcases = _read_prompt_file("./src/prompts/test_case_generation.txt")
        prompt_testdata = _read_prompt_file("./src/prompts/test_data_generation.txt")
        prompt_gherkin = _read_prompt_file("./src/prompts/gherkin_generation.txt")

        # LLM
        access_token = get_access_token()
        llm = get_llm(access_token)

        # Handle provided test data
        provided_name = None
        provided_bytes = None
        if data_mode == "Use provided test data":
            provided_name = provided_testdata.name
            provided_bytes = provided_testdata.read()

        # Build graph
        graph = build_graph().compile()

        initial_state = {
            "story_text": story_text,
            "llm": llm,
            "prompt_phase1": prompt_phase1,
            "prompt_testcases": prompt_testcases,
            "prompt_testdata": prompt_testdata,
            "prompt_gherkin": prompt_gherkin,
            "gherkin_max_files": int(max_gherkin),
            "data_mode": "provided" if provided_bytes else "generate",
            "provided_testdata_filename": provided_name,
            "provided_testdata_bytes": provided_bytes,
            "warnings": [],
        }

        graph.invoke(initial_state)

    st.success("Pipeline completed successfully.")

    # -------------------------
    # Display outputs
    # -------------------------

    runtime_root = Path("./runtime/runs")
    latest_run = sorted(runtime_root.iterdir(), key=lambda p: p.stat().st_mtime)[-1]

    st.header("📄 Outputs")

    tab_tc, tab_td, tab_gh = st.tabs(
        ["Test Cases", "Test Data", "Gherkin"]
    )

    with tab_tc:
        tc_path = latest_run / "TestCases.json"
        if tc_path.exists():
            st.json(json.loads(tc_path.read_text()))
        else:
            st.warning("TestCases.json not found")

    with tab_td:
        td_path = latest_run / "TestData.json"
        if td_path.exists():
            st.json(json.loads(td_path.read_text()))
        else:
            st.warning("TestData.json not found")

    with tab_gh:
        gherkin_dir = latest_run / "gherkin"
        if not gherkin_dir.exists():
            st.warning("No gherkin files found")
        else:
            for feature in sorted(gherkin_dir.glob("*.feature")):
                st.subheader(feature.name)
                st.code(feature.read_text(), language="gherkin")


# IMPORTANT: Streamlit requires this
run_app()
