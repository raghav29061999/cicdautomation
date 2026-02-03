# src/ui/pages/studio.py
from __future__ import annotations

import io
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
                key="dl_testcases_json",
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
                key="dl_testdata_json",
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
                key="dl_gherkin_zip",
            )
        else:
            st.caption("No .feature files found.")

    # Optional: show individual feature downloads
    if gherkin_dir is not None:
        st.markdown("**Individual feature files**")
        for i, fp in enumerate(sorted(gherkin_dir.glob("*.feature")), start=1):
            st.download_button(
                label=f"⬇️ {fp.name}",
                data=fp.read_text(encoding="utf-8", errors="ignore"),
                file_name=fp.name,
                mime="text/plain",
                key=f"dl_feature_{i}_{fp.name}",
            )


def render_studio(run_pipeline_callback) -> None:
    st.title("Studio")
    st.caption("Upload a user story to generate test cases, test data, and Gherkin specs.")

    # Nav back (works even if you’re using multipage)
    nav_cols = st.columns([1, 5])
    with nav_cols[0]:
        if st.button("← Back", use_container_width=True, key="nav_back_about"):
            # Prefer your in-app router (app.py uses st.session_state.route)
            st.session_state.route = "about"
            st.rerun()
    with nav_cols[1]:
        st.write("")

    init_chat()
    render_chat()

    st.divider()

    with st.container(border=True):
        story_file = st.file_uploader("Upload User Story (.txt)", type=["txt"], key="uploader_story_txt")
        data_file = st.file_uploader(
            "Optional: Upload TestData (.json or .xlsx)", type=["json", "xlsx"], key="uploader_testdata_optional"
        )

        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            run = st.button("Run", type="primary", use_container_width=True, key="studio_run_btn")
        with col2:
            clear = st.button("Clear chat", use_container_width=True, key="studio_clear_chat_btn")

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


# --- IMPORTANT: multipage fallback ---
# If someone opens Studio directly from Streamlit's sidebar (not via app.py),
# we won't have the callback wired. Show a helpful message instead of crashing.
if "RUN_PIPELINE_CALLBACK_AVAILABLE" not in st.session_state:
    st.session_state.RUN_PIPELINE_CALLBACK_AVAILABLE = False

if st.session_state.RUN_PIPELINE_CALLBACK_AVAILABLE:
    # app.py will call render_studio(...) with the real callback.
    pass
else:
    st.title("Studio")
    st.info("Open the main app page and use Studio there (or wire the callback via app.py).")
    st.caption("If you see this message, you clicked the Studio multipage entry directly.")
