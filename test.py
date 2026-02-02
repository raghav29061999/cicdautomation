# src/ui/app.py
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Agentic QA Studio",
    page_icon="🧪",
    layout="wide",
)

# Shared session defaults
if "route" not in st.session_state:
    st.session_state.route = "about"  # "about" | "studio"

# Lightweight router
if st.session_state.route == "about":
    from src.ui.pages import About  # type: ignore
    About.render()
else:
    from src.ui.pages import Studio  # type: ignore
    Studio.render()


--------

# src/ui/pages/1_About.py
from __future__ import annotations

import streamlit as st
from src.ui.components.layout import hero, capability_tiles, section


def render() -> None:
    hero(
        title="A new era of AI-led software quality",
        subtitle=(
            "Quality isn’t just a phase. This tool turns user stories into "
            "test cases, test data, and Gherkin specifications — deterministically, "
            "with strong validation and traceability."
        ),
    )

    st.write("")
    capability_tiles(
        tiles=[
            {
                "title": "Agentic Test Design",
                "desc": "Generate test cases from canonical contracts (CIR + Coverage).",
                "icon": "🧠",
            },
            {
                "title": "Synthetic / Provided Data",
                "desc": "Generate test data or upload your own JSON/XLSX and validate it.",
                "icon": "🧾",
            },
            {
                "title": "Gherkin Specs",
                "desc": "Create stakeholder-friendly .feature files with traceability.",
                "icon": "🧩",
            },
        ]
    )

    st.write("")
    with section("What this tool does"):
        st.markdown(
            """
- **Input:** One user story text file  
- **Output:** `TestCases.json`, optional `TestData.json`, and `gherkin/*.feature`  
- **Guarantees:** deterministic IDs, schema validation, and “no hallucination” guardrails  
            """.strip()
        )

    st.write("")
    col1, col2, col3 = st.columns([1, 1, 2], vertical_alignment="center")
    with col1:
        if st.button("See it in action →", use_container_width=True):
            st.session_state.route = "studio"
            st.rerun()

    with col2:
        st.button("Documentation", use_container_width=True, disabled=True)

    with col3:
        st.info("Tip: Keep prompts + contracts versioned. Treat everything as replayable runs.")
---------------
# src/ui/pages/2_Studio.py
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

import streamlit as st

from src.ui.components.layout import top_bar
from src.ui.components.chat import init_chat, chat_message, add_system, add_user, add_assistant

# ---- import your pipeline entry ----
# You should already have something like build_graph() and graph.invoke()
from src.pipeline.graph import build_graph


@dataclass
class RunResult:
    run_id: str
    run_dir: str
    test_cases_path: Optional[str] = None
    test_data_path: Optional[str] = None
    gherkin_dir: Optional[str] = None


def _run_pipeline(story_text: str, data_mode: str, user_data_file: Optional[bytes], user_data_name: Optional[str]) -> RunResult:
    """
    Calls LangGraph pipeline. Assumes your graph nodes already support:
      - story_text
      - data_mode: "generate" | "provided"
      - user_test_data_bytes + user_test_data_name (optional)
    """
    graph = build_graph().compile()

    initial_state = {
        "story_text": story_text,
        "data_mode": data_mode,  # "generate" | "provided"
        "user_test_data_bytes": user_data_file,
        "user_test_data_name": user_data_name,
        # any other fields your pipeline expects:
        "warnings": [],
    }

    final_state = graph.invoke(initial_state)

    return RunResult(
        run_id=str(final_state.get("run_id", "UNKNOWN")),
        run_dir=str(final_state.get("run_dir", "UNKNOWN")),
        test_cases_path=final_state.get("test_cases_path"),
        test_data_path=final_state.get("test_data_path"),
        gherkin_dir=final_state.get("gherkin_dir"),
    )


def render() -> None:
    top_bar(title="Agentic QA Studio", subtitle="Upload a story → generate artifacts → download outputs")

    init_chat()

    # ---------------- Sidebar ----------------
    with st.sidebar:
        st.markdown("### Inputs")

        story_file = st.file_uploader("Upload user story (.txt)", type=["txt"])
        st.markdown("### Test data mode")
        data_mode = st.radio(
            "Choose mode",
            options=["Generate test data", "Provide my own test data"],
            index=0,
        )
        data_mode_norm = "generate" if data_mode == "Generate test data" else "provided"

        user_data = None
        user_data_name = None
        if data_mode_norm == "provided":
            user_data_up = st.file_uploader("Upload test data (JSON / XLSX)", type=["json", "xlsx"])
            if user_data_up is not None:
                user_data = user_data_up.getvalue()
                user_data_name = user_data_up.name

        st.markdown("---")
        run_clicked = st.button("🚀 Run", use_container_width=True)

        st.markdown("---")
        if st.button("← Back to About", use_container_width=True):
            st.session_state.route = "about"
            st.rerun()

    # ---------------- Main chat-like view ----------------
    # show transcript
    for m in st.session_state.chat:
        chat_message(m["role"], m["content"])

    if run_clicked:
        if story_file is None:
            add_system("Please upload a user story file first.")
            st.rerun()

        story_text = story_file.getvalue().decode("utf-8", errors="replace").strip()
        if not story_text:
            add_system("Your story file is empty.")
            st.rerun()

        add_user("Run the pipeline for this story.")
        add_assistant("Running… generating Phase-1 artifacts, test cases, test data, and gherkin outputs.")

        with st.spinner("Executing pipeline…"):
            try:
                result = _run_pipeline(
                    story_text=story_text,
                    data_mode=data_mode_norm,
                    user_data_file=user_data,
                    user_data_name=user_data_name,
                )
            except Exception as e:
                add_system(f"Pipeline failed: {type(e).__name__}: {e}")
                st.rerun()

        add_assistant(
            "\n".join(
                [
                    f"✅ Run completed",
                    f"- run_id: {result.run_id}",
                    f"- run_dir: {result.run_dir}",
                    f"- test_cases: {result.test_cases_path or 'not found'}",
                    f"- test_data: {result.test_data_path or 'not found'}",
                    f"- gherkin_dir: {result.gherkin_dir or 'not found'}",
                ]
            )
        )

        # Download helpers (optional)
        st.session_state.last_run = result.__dict__
        st.rerun()

    # ---------------- Downloads panel ----------------
    if "last_run" in st.session_state:
        st.markdown("### Outputs")

        colA, colB, colC = st.columns(3)
        with colA:
            st.write("**TestCases.json**")
            st.caption("Generated per run")
            # If you want direct downloads, you can read file bytes from disk here.

        with colB:
            st.write("**TestData.json**")
            st.caption("Generated or validated from upload")

        with colC:
            st.write("**Gherkin files**")
            st.caption("One scenario per file")
---
# src/ui/components/layout.py
from __future__ import annotations

import streamlit as st


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div style="padding: 18px 20px; border-radius: 14px; background: linear-gradient(90deg,#ffe6c7,#e9e0ff,#d6f0ff);">
          <h1 style="margin:0;">{title}</h1>
          <p style="margin:8px 0 0 0; font-size: 16px; opacity: 0.9;">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def capability_tiles(tiles: list[dict]) -> None:
    cols = st.columns(len(tiles))
    for c, t in zip(cols, tiles):
        with c:
            st.markdown(
                f"""
                <div style="border:1px solid rgba(255,255,255,0.08); border-radius:14px; padding:14px; background: rgba(255,255,255,0.03); min-height: 120px;">
                  <div style="font-size:28px;">{t.get("icon","")}</div>
                  <div style="font-weight:700; font-size:16px; margin-top:6px;">{t.get("title","")}</div>
                  <div style="opacity:0.9; font-size:13px; margin-top:6px;">{t.get("desc","")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def top_bar(title: str, subtitle: str) -> None:
    st.markdown(f"## {title}")
    st.caption(subtitle)


def section(title: str):
    return st.expander(title, expanded=True)
---
# src/ui/components/chat.py
from __future__ import annotations

import streamlit as st


def init_chat() -> None:
    if "chat" not in st.session_state:
        st.session_state.chat = [
            {"role": "assistant", "content": "Welcome. Upload a story and click Run to generate artifacts."}
        ]


def chat_message(role: str, content: strίο:
    with st.chat_message(role):
        st.write(content)


def add_system(text: str) -> None:
    st.session_state.chat.append({"role": "assistant", "content": f"⚠️ {text}"})


def add_user(text: str) -> None:
    st.session_state.chat.append({"role": "user", "content": text})


def add_assistant(text: str) -> None:
    st.session_state.chat.append({"role": "assistant", "content": text})
---
from __future__ import annotations
import streamlit as st


def render_flip_cards(cards: list[dict]) -> None:
    """
    cards = [
      {
        "front_title": "...",
        "front_icon": "🧠",
        "back_title": "...",
        "back_text": "..."
      }
    ]
    """
    css = """
    <style>
    .flip-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 20px;
    }
    .flip-card {
        background: transparent;
        width: 100%;
        height: 180px;
        perspective: 1000px;
    }
    .flip-card-inner {
        position: relative;
        width: 100%;
        height: 100%;
        text-align: center;
        transition: transform 0.6s;
        transform-style: preserve-3d;
    }
    .flip-card:hover .flip-card-inner {
        transform: rotateY(180deg);
    }
    .flip-card-front, .flip-card-back {
        position: absolute;
        width: 100%;
        height: 100%;
        backface-visibility: hidden;
        border-radius: 14px;
        padding: 18px;
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        border: 1px solid rgba(255,255,255,0.1);
    }
    .flip-card-front {
        background: linear-gradient(135deg, #1f2937, #111827);
    }
    .flip-card-back {
        background: linear-gradient(135deg, #2563eb, #1e40af);
        transform: rotateY(180deg);
    }
    </style>
    """

    html = '<div class="flip-grid">'
    for c in cards:
        html += f"""
        <div class="flip-card">
          <div class="flip-card-inner">
            <div class="flip-card-front">
              <div style="font-size:34px">{c.get("front_icon","")}</div>
              <h4>{c.get("front_title","")}</h4>
            </div>
            <div class="flip-card-back">
              <h4>{c.get("back_title","")}</h4>
              <p style="font-size:14px; opacity:0.9">{c.get("back_text","")}</p>
            </div>
          </div>
        </div>
        """
    html += "</div>"

    st.markdown(css + html, unsafe_allow_html=True)
---
from src.ui.components.flip_cards import render_flip_cards

render_flip_cards(
    cards=[
        {
            "front_icon": "🧠",
            "front_title": "Agentic Test Design",
            "back_title": "What it does",
            "back_text": "Transforms user stories into validated test cases using canonical contracts and deterministic pipelines."
        },
        {
            "front_icon": "🧾",
            "front_title": "Test Data Intelligence",
            "back_title": "Flexible data",
            "back_text": "Generate synthetic datasets or validate user-provided JSON/XLSX without guessing."
        },
        {
            "front_icon": "🧩",
            "front_title": "Gherkin Automation",
            "back_title": "Business-ready",
            "back_text": "Produces readable, traceable Gherkin feature files for stakeholders and automation."
        }
    ]
)
