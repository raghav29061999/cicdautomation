# src/ui/pages/about.py
from __future__ import annotations

import uuid
import streamlit as st
from src.ui.components.flip_cards import render_flip_cards


def render_about(on_cta_click) -> None:
    """
    About / Landing page.

    `on_cta_click` is a callback that switches navigation to Studio.
    """

    # ---- Create a stable-per-session unique suffix for widget keys ----
    if "about_key_salt" not in st.session_state:
        st.session_state.about_key_salt = uuid.uuid4().hex[:8]
    salt = st.session_state.about_key_salt

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
        if st.button(
            "See it in action →",
            type="primary",
            use_container_width=True,
            key=f"cta_see_action_{salt}",
        ):
            if callable(on_cta_click):
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
