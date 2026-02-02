# src/ui/components/chat.py
from __future__ import annotations

import streamlit as st

DEFAULT_WELCOME = "Welcome. Upload a story and click Run to generate artifacts."


def init_chat(welcome: str = DEFAULT_WELCOME) -> None:
    """
    Initialize chat history in Streamlit session state.
    """
    if "chat" not in st.session_state or not isinstance(st.session_state.chat, list):
        st.session_state.chat = [{"role": "assistant", "content": welcome}]


def render_chat() -> None:
    """
    Render all chat messages stored in session state.
    """
    init_chat()
    for msg in st.session_state.chat:
        role = msg.get("role", "assistant")
        content = msg.get("content", "")
        chat_message(role=role, content=content)


def chat_message(role: str, content: str) -> None:
    """
    Render a single chat message.
    Allowed roles: 'user' | 'assistant' | 'system' (system rendered as assistant with prefix).
    """
    role = (role or "assistant").strip().lower()
    if role not in {"user", "assistant", "system"}:
        role = "assistant"

    content = "" if content is None else str(content)

    if role == "system":
        with st.chat_message("assistant"):
            st.write(f"⚙️ {content}")
        return

    with st.chat_message(role):
        st.write(content)


def add_system(text: str) -> None:
    """
    Append a system-style assistant message to chat history.
    """
    init_chat()
    st.session_state.chat.append({"role": "system", "content": str(text)})


def add_user(text: str) -> None:
    """
    Append a user message to chat history.
    """
    init_chat()
    st.session_state.chat.append({"role": "user", "content": str(text)})


def add_assistant(text: str) -> None:
    """
    Append an assistant message to chat history.
    """
    init_chat()
    st.session_state.chat.append({"role": "assistant", "content": str(text)})


def clear_chat(welcome: str = DEFAULT_WELCOME) -> None:
    """
    Clear chat history and re-seed with welcome message.
    """
    st.session_state.chat = [{"role": "assistant", "content": welcome}]

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
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
----------------------------------------------------------------------------------------------------------------------


# src/main.py
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def launch_ui():
    """
    Launch Streamlit UI.
    """
    ui_app = Path(__file__).parent / "ui" / "app.py"

    if not ui_app.exists():
        raise RuntimeError("UI entrypoint not found at src/ui/app.py")

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(ui_app),
    ]
    subprocess.run(cmd, check=True)


def run_cli(story_path: str):
    """
    Run pipeline in CLI mode (no UI).
    """
    from src.ingestion.story_loader import load_user_stories
    from src.pipeline.graph import build_graph
    from src.utils.llm import get_llm, get_access_token
    from dotenv import load_dotenv

    load_dotenv()

    stories = load_user_stories(Path(story_path).parent)
    if not stories:
        raise SystemExit(f"No story found in {story_path}")

    story = next(s for s in stories if s.filename == Path(story_path).name)

    llm = get_llm(get_access_token())

    graph = build_graph().compile()

    initial_state = {
        "story_id": story.story_id,
        "story_filename": story.filename,
        "story_text": story.raw_text,
        "llm": llm,
        "data_mode": "generate",  # or "provided"
        "warnings": [],
    }

    final_state = graph.invoke(initial_state)

    print("\nPipeline completed successfully")
    print("Run ID:", final_state.get("run_id"))
    print("Output dir:", final_state.get("run_dir"))


def main():
    parser = argparse.ArgumentParser(description="Agentic Test Generator")
    parser.add_argument(
        "--story",
        type=str,
        help="Run pipeline in CLI mode with a user story file",
    )

    args = parser.parse_args()

    if args.story:
        run_cli(args.story)
    else:
        launch_ui()


if __name__ == "__main__":
    main()

