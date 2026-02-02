# src/main.py
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

from src.ui.launcher import launch_ui   # or wherever your launch_ui lives
from src.pipeline.graph import build_graph
from src.utils import get_access_token, get_llm, _read_prompt_file
from src.phase1.writer import ensure_runtime_root  # if you have something like this


def run_pipeline(story_text: str, data_file) -> dict:
    """
    UI callback.
    `data_file` is a Streamlit UploadedFile or None.
    """
    load_dotenv()

    runtime_root = os.getenv("RUNTIME_ROOT", "./runtime")
    Path(runtime_root).mkdir(parents=True, exist_ok=True)

    # prompts
    prompt_phase1 = _read_prompt_file(os.getenv("PROMPT_PHASE1_PATH", "./src/prompts/phase1_runtime_artifacts.txt"))
    prompt_testcases = _read_prompt_file(os.getenv("PROMPT_TESTCASES_PATH", "./src/prompts/test_case_generation.txt"))
    prompt_testdata = _read_prompt_file(os.getenv("PROMPT_TESTDATA_PATH", "./src/prompts/test_data_generation.txt"))
    prompt_gherkin = _read_prompt_file(os.getenv("PROMPT_GHERKIN_PATH", "./src/prompts/gherkin_generation.txt"))

    # llm
    token = get_access_token()
    llm = get_llm(token)

    # graph
    graph = build_graph().compile()

    # IMPORTANT: decide mode based on whether user uploaded data_file
    data_mode = "provided" if data_file is not None else "generate"

    # build state
    initial_state = {
        "story_text": story_text,
        "prompt_phase1": prompt_phase1,
        "prompt_testcases": prompt_testcases,
        "prompt_testdata": prompt_testdata,
        "prompt_gherkin": prompt_gherkin,
        "llm": llm,
        "runtime_root": runtime_root,
        "data_mode": data_mode,
        "user_test_data_file": data_file,  # node_ingest_user_test_data should read this
        "warnings": [],
    }

    final_state = graph.invoke(initial_state)

    # Return minimal UI-friendly info
    return {
        "run_id": final_state.get("run_id"),
        "run_dir": final_state.get("run_dir"),
        "warnings": final_state.get("warnings", []),
        "outputs": final_state.get("outputs", []),
    }


def main():
    # ✅ THIS is the key fix: pass callback into launch_ui
    launch_ui(run_pipeline_callback=run_pipeline)


if __name__ == "__main__":
    main()
