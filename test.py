# src/ui/app.py
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.pipeline.graph import build_graph


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _get_llm():
    # Keep local import so UI loads without env until runtime
    try:
        from src.utils.llm import get_llm, get_access_token  # type: ignore
    except Exception:
        from src.utils import get_llm, get_access_token  # type: ignore

    token = get_access_token()
    return get_llm(token)


def _run_pipeline(story_text: str, data_file):
    load_dotenv()

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

    # Save optional uploaded TestData to runtime/uploads
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


# ---------------- Streamlit app (single entry) ----------------

st.set_page_config(page_title="Agentic QA Studio", page_icon="🧪", layout="wide")

# Internal router state
if "route" not in st.session_state:
    st.session_state.route = "about"  # "about" | "studio"


def _go_about():
    st.session_state.route = "about"
    st.rerun()


def _go_studio():
    st.session_state.route = "studio"
    st.rerun()


# Render
if st.session_state.route == "about":
    from src.ui.pages.about import render_about
    render_about(on_cta_click=_go_studio)
else:
    from src.ui.pages.studio import render_studio
    render_studio(run_pipeline_callback=_run_pipeline, on_back=_go_about)
------------------------------------------------
-----------------------------------------------



# src/ui/pages/about.py
from __future__ import annotations

import streamlit as st
from src.ui.components.flip_cards import render_flip_cards


def render_about(on_cta_click) -> None:
    st.title("A new era of AI-led software quality")
    st.write(
        "Quality isn’t just a phase. This tool turns user stories into **test cases**, **test data**, "
        "and **Gherkin specifications** — deterministically, with validation and traceability."
    )

    st.divider()
    render_flip_cards()
    st.divider()

    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("See it in action →", type="primary", use_container_width=True, key="cta_to_studio"):
            if callable(on_cta_click):
                on_cta_click()

    with col2:
        st.caption(
            "Tip: Start with one story. Optionally upload your own test data (JSON/XLSX) "
            "to drive test cases and Gherkin."
        )

    st.subheader("What this tool does")
    st.markdown(
        "- **Input:** one user story `.txt`\n"
        "- **Output:** `TestCases.json`, `TestData.json` (optional), and `.feature` files\n"
        "- **Guarantees:** schema validation, deterministic IDs, traceability to acceptance criteria\n"
    )


------------------------------------------------
-----------------------------------------------


# src/ui/pages/studio.py
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import streamlit as st

from src.ui.components.chat import init_chat, render_chat, add_user, add_assistant


def _zip_feature_files(run_dir: Path) -> bytes:
    # Find feature files anywhere under run_dir
    feature_files = sorted(run_dir.rglob("*.feature"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in feature_files:
            # store only filename to keep zip tidy
            zf.writestr(fp.name, fp.read_text(encoding="utf-8", errors="ignore"))
    buf.seek(0)
    return buf.read()


def _render_downloads(run_dir: str | None) -> None:
    if not run_dir:
        return

    p = Path(run_dir)
    if not p.exists():
        st.warning(f"Run directory not found: {run_dir}")
        return

    st.subheader("Downloads")

    testcases = p / "TestCases.json"
    testdata = p / "TestData.json"

    c1, c2, c3 = st.columns(3)

    with c1:
        if testcases.exists():
            st.download_button(
                "⬇️ TestCases.json",
                data=testcases.read_bytes(),
                file_name="TestCases.json",
                mime="application/json",
                use_container_width=True,
                key="dl_testcases",
            )
        else:
            st.caption("TestCases.json not found.")

    with c2:
        if testdata.exists():
            st.download_button(
                "⬇️ TestData.json",
                data=testdata.read_bytes(),
                file_name="TestData.json",
                mime="application/json",
                use_container_width=True,
                key="dl_testdata",
            )
        else:
            st.caption("TestData.json not present (maybe BYO data or skipped).")

    with c3:
        feature_files = list(p.rglob("*.feature"))
        if feature_files:
            zipped = _zip_feature_files(p)
            st.download_button(
                "⬇️ Gherkin ZIP",
                data=zipped,
                file_name="gherkin_features.zip",
                mime="application/zip",
                use_container_width=True,
                key="dl_gherkin_zip",
            )
        else:
            st.caption("No .feature files found.")

    # Optional: list individual feature downloads
    feature_files = sorted(p.rglob("*.feature"))
    if feature_files:
        st.markdown("**Individual feature files**")
        for fp in feature_files:
            st.download_button(
                f"⬇️ {fp.name}",
                data=fp.read_text(encoding="utf-8", errors="ignore"),
                file_name=fp.name,
                mime="text/plain",
                key=f"dl_{fp.name}",
            )


def render_studio(run_pipeline_callback, on_back) -> None:
    st.title("Studio")
    st.caption("Upload a user story to generate test cases, test data, and Gherkin specs.")

    top = st.columns([1, 5])
    with top[0]:
        if st.button("← Back", use_container_width=True, key="btn_back_about"):
            if callable(on_back):
                on_back()

    init_chat()
    render_chat()

    st.divider()

    with st.container(border=True):
        story_file = st.file_uploader("Upload User Story (.txt)", type=["txt"], key="upl_story")
        data_file = st.file_uploader("Optional: Upload TestData (.json or .xlsx)", type=["json", "xlsx"], key="upl_data")

        col1, col2, _ = st.columns([1, 1, 3])
        run = col1.button("Run", type="primary", use_container_width=True, key="btn_run")
        clear = col2.button("Clear chat", use_container_width=True, key="btn_clear")

        if clear:
            st.session_state.chat = [
                {"role": "assistant", "content": "Welcome. Upload a story and click Run to generate artifacts."}
            ]
            st.session_state.pop("last_run", None)
            st.rerun()

        if run:
            if not story_file:
                add_assistant("Please upload a user story file first.")
                st.rerun()

            story_text = story_file.read().decode("utf-8", errors="ignore").strip()
            if not story_text:
                add_assistant("Uploaded story was empty. Please upload a valid user story text file.")
                st.rerun()

            add_user(f"Uploaded story: {story_file.name}")

            try:
                result = run_pipeline_callback(story_text=story_text, data_file=data_file)
            except Exception as e:
                add_assistant(f"Pipeline failed: {type(e).__name__}: {e}")
                st.rerun()

            run_id = (result or {}).get("run_id", "UNKNOWN")
            run_dir = (result or {}).get("run_dir")

            st.session_state.last_run = {"run_id": run_id, "run_dir": run_dir, "result": result}
            add_assistant(f"✅ Run completed. run_id={run_id}")

            st.success("Run completed.")
            st.json(result)

    last = st.session_state.get("last_run")
    if last:
        _render_downloads(last.get("run_dir"))
