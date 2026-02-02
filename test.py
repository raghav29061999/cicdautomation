from __future__ import annotations

import streamlit.components.v1 as components


def render_flip_cards() -> None:
    """
    Renders hover flip-cards using a raw HTML+CSS block.

    Why components.html?
    - Streamlit's st.markdown can display raw HTML as text if unsafe_allow_html isn't used
    - Even with unsafe_allow_html, complex CSS/hover effects are unreliable
    - components.html renders consistently
    """
    css = """
    <style>
      .cards { display:flex; gap:16px; flex-wrap:wrap; }
      .flip-card { background: transparent; width: 260px; height: 150px; perspective: 1000px; }
      .flip-card-inner {
        position: relative; width: 100%; height: 100%;
        transition: transform 0.6s; transform-style: preserve-3d;
      }
      .flip-card:hover .flip-card-inner { transform: rotateY(180deg); }
      .flip-card-front, .flip-card-back {
        position: absolute; width: 100%; height: 100%;
        backface-visibility: hidden;
        border-radius: 14px; padding: 16px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.22);
        display:flex; flex-direction:column; justify-content:center;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
      }
      .flip-card-front {
        background: linear-gradient(135deg, #0b1220, #1e3a8a);
        color: white;
      }
      .flip-card-back {
        background: linear-gradient(135deg, #111827, #334155);
        color: white;
        transform: rotateY(180deg);
      }
      .icon { font-size: 30px; margin-bottom: 8px; }
      .title { font-size: 16px; font-weight: 800; margin: 0; }
      .desc { font-size: 13px; opacity: 0.92; margin: 8px 0 0 0; line-height: 1.25; }
      .tag { font-size: 12px; opacity: 0.85; margin-top: 10px; }
    </style>
    """

    html = css + """
    <div class="cards">
      <div class="flip-card">
        <div class="flip-card-inner">
          <div class="flip-card-front">
            <div class="icon">🧠</div>
            <p class="title">Agentic Test Design</p>
            <p class="desc">Story → CIR → deterministic test cases</p>
            <p class="tag">Validation-first</p>
          </div>
          <div class="flip-card-back">
            <p class="title">Deterministic outputs</p>
            <p class="desc">Stable IDs, strict schemas, traceability to acceptance criteria.</p>
          </div>
        </div>
      </div>

      <div class="flip-card">
        <div class="flip-card-inner">
          <div class="flip-card-front">
            <div class="icon">🧪</div>
            <p class="title">Test Data Intelligence</p>
            <p class="desc">Generate or ingest JSON/XLSX data</p>
            <p class="tag">Data-driven</p>
          </div>
          <div class="flip-card-back">
            <p class="title">Flexible input modes</p>
            <p class="desc">Bring your own test data or synthesize minimal datasets for coverage.</p>
          </div>
        </div>
      </div>

      <div class="flip-card">
        <div class="flip-card-inner">
          <div class="flip-card-front">
            <div class="icon">📄</div>
            <p class="title">Gherkin Specs</p>
            <p class="desc">Business-readable scenarios</p>
            <p class="tag">Executable-ready</p>
          </div>
          <div class="flip-card-back">
            <p class="title">One scenario per file</p>
            <p class="desc">Clean feature files with traceability in comments (no IDs in steps).</p>
          </div>
        </div>
      </div>
    </div>
    """

    components.html(html, height=190, scrolling=False)


-----------------------------------------------------------------------------------------------------------------------------
----------------------------------------------------------------------------------------------------------------------

-----------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
--------------------------------------------------------------------------------------------------
from __future__ import annotations

import streamlit as st
from src.ui.components.flip_cards import render_flip_cards


def render_about(on_cta_click) -> None:
    """
    About / Landing page.

    `on_cta_click` is a callback that switches navigation to Studio.
    This keeps routing logic outside page code.
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
            on_cta_click()

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


-------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
----------------------------------------------------------------------------------------------------------------------


from __future__ import annotations

import json
import streamlit as st

from src.ui.components.chat import init_chat, render_chat, add_user, add_assistant


def render_studio(run_pipeline_callback) -> None:
    """
    Studio / App page.

    `run_pipeline_callback(story_text: str, data_file)` should:
      - run the pipeline (phase1 -> test_cases -> (optional)test_data -> gherkin)
      - return a small dict (run_id, run_dir, outputs list, warnings, etc.)
    """
    st.title("Studio")
    st.caption("Upload a user story to generate test cases, test data, and Gherkin specs.")

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
            add_assistant(f"✅ Run completed. run_id={run_id}")

            # Show a compact summary
            st.success("Run completed.")
            st.json(result)

            # Optional: show downloadable content if you include paths/strings
            # (kept generic since your pipeline may write files to runtime)
            st.info("Check runtime output folder for generated artifacts.")
            st.rerun()

-------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
------------------------------------------
def launch_ui(run_pipeline_callback) -> None:
    """
    Launch Streamlit UI with two pages: About + Studio.
    We do NOT depend on Streamlit multipage discovery to avoid blank pages.
    """
    import streamlit as st
    from src.ui.pages.about import render_about
    from src.ui.pages.studio import render_studio

    st.set_page_config(page_title="Agentic Test Design", layout="wide")

    if "ui_page" not in st.session_state:
        st.session_state.ui_page = "about"

    def go_about():
        st.session_state.ui_page = "about"
        st.rerun()

    def go_studio():
        st.session_state.ui_page = "studio"
        st.rerun()

    with st.sidebar:
        st.title("Agentic Test Design")
        choice = st.radio("Navigate", ["About", "Studio"], index=0 if st.session_state.ui_page == "about" else 1)
        if choice == "About":
            st.session_state.ui_page = "about"
        else:
            st.session_state.ui_page = "studio"

        st.divider()
        if st.button("About"):
            go_about()
        if st.button("Studio"):
            go_studio()

    if st.session_state.ui_page == "about":
        render_about(on_cta_click=go_studio)
    else:
        render_studio(run_pipeline_callback=run_pipeline_callback)


