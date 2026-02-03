src/ui/pages/about.py
from __future__ import annotations

import streamlit as st
from src.ui.components.flip_cards import render_flip_cards


def render_about(on_cta_click) -> None:
    """
    About / Landing page.
    `on_cta_click` is a callback used by app-router. In multipage mode, it can be ignored.
    """
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
        if st.button("See it in action →", type="primary", use_container_width=True):
            # If provided (router mode), use callback; else use Streamlit multipage switch.
            if callable(on_cta_click):
                on_cta_click()
            else:
                try:
                    st.switch_page("pages/studio.py")
                except Exception:
                    # fallback: stay on page
                    st.info("Navigation unavailable. Please open the Studio page from the sidebar.")
    with col2:
        st.caption(
            "Tip: Start with a single story. You can optionally upload your own test data (JSON/XLSX) "
            "to drive both test cases and Gherkin."
        )

    st.subheader("What this tool does")
    st.markdown(
        "- **Input:** one user story `.txt`\n"
        "- **Output:** `TestCases.json`, `TestData.json` (optional), and `.feature` files\n"
        "- **Guarantees:** schema validation, deterministic IDs, traceability to acceptance criteria\n"
    )


# --- IMPORTANT: make the page render when opened directly from Streamlit sidebar ---
# Streamlit executes this file when you click "about" in the sidebar.
render_about(on_cta_click=None)
---------------------------------------------------
-----------------------------------
src/ui/pages/studio.py
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import streamlit as st

from src.ui.components.chat import init_chat, render_chat, add_user, add_assistant


def _safe_read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except Exception:
        return b""


def _zip_gherkin_folder(gherkin_dir: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(gherkin_dir.glob("*.feature")):
            zf.writestr(p.name, p.read_text(encoding="utf-8", errors="ignore"))
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

    # Common expected outputs (adjust if your writer names differ)
    testcases = p / "TestCases.json"
    testdata = p / "TestData.json"

    # Gherkin output location variants
    gherkin_dir_candidates = [
        p / "gherkin",
        p / "gherkin_files",
        p / "features",
        p,  # sometimes written directly in run dir
    ]
    gherkin_dir = next((d for d in gherkin_dir_candidates if d.exists() and any(d.glob("*.feature"))), None)

    cols = st.columns(3)

    with cols[0]:
        if testcases.exists():
            st.download_button(
                label="⬇️ TestCases.json",
                data=_safe_read_bytes(testcases),
                file_name="TestCases.json",
                mime="application/json",
                use_container_width=True,
            )
        else:
            st.info("TestCases.json not found in run folder.")

    with cols[1]:
        if testdata.exists():
            st.download_button(
                label="⬇️ TestData.json",
                data=_safe_read_bytes(testdata),
                file_name="TestData.json",
                mime="application/json",
                use_container_width=True,
            )
        else:
            st.caption("TestData.json not generated (or not present).")

    with cols[2]:
        if gherkin_dir is not None:
            zipped = _zip_gherkin_folder(gherkin_dir)
            st.download_button(
                label="⬇️ Gherkin (.feature) ZIP",
                data=zipped,
                file_name="gherkin_features.zip",
                mime="application/zip",
                use_container_width=True,
            )
        else:
            st.caption("No .feature files found.")

    # Optional: show individual feature downloads
    if gherkin_dir is not None:
        st.markdown("**Individual feature files**")
        for fp in sorted(gherkin_dir.glob("*.feature")):
            st.download_button(
                label=f"⬇️ {fp.name}",
                data=fp.read_text(encoding="utf-8", errors="ignore"),
                file_name=fp.name,
                mime="text/plain",
            )


def render_studio(run_pipeline_callback) -> None:
    st.title("Studio")
    st.caption("Upload a user story to generate test cases, test data, and Gherkin specs.")

    # Nav back (works even if you’re using multipage)
    nav_cols = st.columns([1, 5])
    with nav_cols[0]:
        if st.button("← Back", use_container_width=True):
            try:
                st.switch_page("pages/about.py")
            except Exception:
                st.info("Use the sidebar to open About.")
    with nav_cols[1]:
        st.write("")

    init_chat()
    render_chat()

    st.divider()

    with st.container(border=True):
        story_file = st.file_uploader("Upload User Story (.txt)", type=["txt"])
        data_file = st.file_uploader("Optional: Upload TestData (.json or .xlsx)", type=["json", "xlsx"])

        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            run = st.button("Run", type="primary", use_container_width=True)
        with col2:
            clear = st.button("Clear chat", use_container_width=True)

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
                add_assistant("Uploaded file was empty. Please upload a valid user story text file.")
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

    # Render downloads for last run (persisted across reruns)
    last = st.session_state.get("last_run")
    if last:
        _render_downloads(last.get("run_dir"))


# --- IMPORTANT: make the page render when opened directly from Streamlit sidebar ---
# In multipage mode, this file is executed directly. We can't run without callback,
# so we provide an instructive fallback.
if "RUN_PIPELINE_CALLBACK_AVAILABLE" not in st.session_state:
    st.session_state.RUN_PIPELINE_CALLBACK_AVAILABLE = False

if st.session_state.RUN_PIPELINE_CALLBACK_AVAILABLE:
    # app.py will call render_studio(...) with the real callback.
    pass
else:
    st.title("Studio")
    st.info("Open the main app page and use Studio there (or wire the callback via app.py).")
    st.caption("If you see this message, you clicked the Studio multipage entry directly.")

----------------------------

-----------------

src/ui/app.py
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.pipeline.graph import build_graph


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def _get_llm():
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


st.set_page_config(
    page_title="Agentic QA Studio",
    page_icon="🧪",
    layout="wide",
)

# Make Studio multipage page capable of knowing callback exists
st.session_state.RUN_PIPELINE_CALLBACK_AVAILABLE = True

# Sidebar nav (this also solves “can’t go back”)
if "route" not in st.session_state:
    st.session_state.route = "about"

route = st.sidebar.radio(
    "Navigation",
    options=["about", "studio"],
    index=0 if st.session_state.route == "about" else 1,
)
st.session_state.route = route

if st.session_state.route == "about":
    from src.ui.pages.about import render_about
    render_about(on_cta_click=lambda: st.session_state.update({"route": "studio"}) or st.rerun())
else:
    from src.ui.pages.studio import render_studio
    render_studio(run_pipeline_callback=_run_pipeline)
