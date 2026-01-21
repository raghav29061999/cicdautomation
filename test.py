# src/main.py
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

import streamlit as st
from dotenv import load_dotenv

from src.pipeline.graph import build_graph
from src.utils import _read_prompt_file, get_access_token, get_llm


# ------------------------
# Streamlit App
# ------------------------

def main():
    load_dotenv()

    st.set_page_config(
        page_title="Agentic Test Design",
        layout="wide"
    )

    st.title("🧠 Agentic Test Design Pipeline")
    st.caption("Upload a user story → get TestCases.json + TestData.json")

    # ------------------------
    # Upload User Story
    # ------------------------
    uploaded_file = st.file_uploader(
        "Upload User Story (.txt)",
        type=["txt"]
    )

    if not uploaded_file:
        st.info("Please upload a user story text file to begin.")
        return

    story_text = uploaded_file.read().decode("utf-8")

    st.subheader("📄 User Story Preview")
    st.text_area(
        label="User Story",
        value=story_text,
        height=200
    )

    # ------------------------
    # Run Pipeline Button
    # ------------------------
    if st.button("🚀 Generate Test Artifacts", type="primary"):
        with st.spinner("Running agentic pipeline..."):
            try:
                run_pipeline(story_text)
            except Exception as e:
                st.error("Pipeline execution failed")
                st.exception(e)
                return

    # ------------------------
    # Show Outputs
    # ------------------------
    runtime_root = Path(os.getenv("RUNTIME_ROOT", "./runtime"))
    runs_dir = runtime_root / "runs"

    if runs_dir.exists():
        latest_run = sorted(runs_dir.iterdir(), key=os.path.getmtime)[-1]

        st.success(f"✅ Run completed: {latest_run.name}")

        show_outputs(latest_run)


# ------------------------
# Pipeline Runner
# ------------------------

def run_pipeline(story_text: str):
    # Load prompts
    prompt_phase1 = _read_prompt_file(
        os.getenv("PROMPT_PHASE1_PATH", "./src/prompts/phase1_runtime_artifacts.txt")
    )
    prompt_testcases = _read_prompt_file(
        os.getenv("PROMPT_TESTCASES_PATH", "./src/prompts/test_case_generation.txt")
    )
    prompt_testdata = _read_prompt_file(
        os.getenv("PROMPT_TESTDATA_PATH", "./src/prompts/test_data_generation.txt")
    )

    # LLM
    access_token = get_access_token()
    llm = get_llm(access_token)

    # Build graph
    graph = build_graph().compile()

    initial_state = {
        "story_text": story_text,
        "prompt_phase1": prompt_phase1,
        "prompt_testcases": prompt_testcases,
        "prompt_testdata": prompt_testdata,
        "llm": llm,
        "warnings": [],
    }

    graph.invoke(initial_state)


# ------------------------
# Output Viewer
# ------------------------

def show_outputs(run_dir: Path):
    st.subheader("📦 Generated Artifacts")

    for file in run_dir.iterdir():
        if not file.is_file():
            continue

        st.markdown(f"### {file.name}")

        if file.suffix == ".json":
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)

            st.json(data)

            st.download_button(
                label=f"⬇️ Download {file.name}",
                data=json.dumps(data, indent=2),
                file_name=file.name,
                mime="application/json"
            )
        else:
            with open(file, "r", encoding="utf-8") as f:
                content = f.read()

            st.text_area(
                label=file.name,
                value=content,
                height=200
            )


if __name__ == "__main__":
    main()
