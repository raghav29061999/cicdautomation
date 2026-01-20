"""
pipeline package

LangGraph orchestration layer:
- Defines shared State
- Defines node functions
- Defines graph wiring
"""
------------------

src/pipeline/state.py


from __future__ import annotations

from typing import Any, Dict, Optional, TypedDict


class PipelineState(TypedDict, total=False):
    """
    Shared LangGraph state.

    NOTE:
    - Keep state serializable when possible.
    - Store large artifacts as dicts/strings (not custom objects) for portability.
    """

    # Inputs
    story_id: str
    story_filename: str
    story_text: str

    # Prompts (loaded text)
    prompt_phase1: str
    prompt_testcases: str

    # LLM handle (non-serializable; ok for local runs)
    llm: Any

    # Phase-1 outputs
    run_id: str
    artifacts: Dict[str, Any]  # filenames -> content (dict for json, str for md)

    # Test case outputs
    test_cases_obj: Dict[str, Any]  # JSON object {run_id, test_cases:[...]}

    # Runtime output path
    run_dir: str

    # Diagnostics
    warnings: list[str]



-------------


src/pipeline/nodes.py


from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from pipeline.state import PipelineState

from phase1.parser import parse_phase1_output
from phase1.writer import write_artifacts_to_run_dir
from phase1.models import ArtifactBundle

from test_design.designer import design_test_cases, TestCaseDesignConfig


def _render_prompt_with_story(prompt_template: str, story_text: str) -> str:
    """
    Your Phase-1 prompt uses:
    NOW PROCESS THIS USER STORY:
    """<USER_STORY_TEXT>"""

    We replace the placeholder safely.
    """
    return prompt_template.replace('"""<USER_STORY_TEXT>"""', f'"""{story_text}"""')


def node_phase1_generate(state: PipelineState) -> PipelineState:
    """
    Calls LLM for Phase-1 artifacts generation, parses the output into an ArtifactBundle.
    """
    llm = state["llm"]
    prompt_phase1 = state["prompt_phase1"]
    story_text = state["story_text"]

    prompt = _render_prompt_with_story(prompt_phase1, story_text)

    # Azure OpenAI usage pattern (as you described)
    # llm.invoke("...") -> returns text or object with content
    raw_out = llm.invoke(prompt)

    # Normalize output to string
    if isinstance(raw_out, str):
        out_text = raw_out
    else:
        # common patterns: .content or str(obj)
        out_text = getattr(raw_out, "content", None) or str(raw_out)

    parse_result = parse_phase1_output(out_text)

    bundle: ArtifactBundle = parse_result.bundle
    warnings = parse_result.warnings or []

    state["run_id"] = bundle.run_id
    state["artifacts"] = bundle.artifacts
    state["warnings"] = warnings
    return state


def node_phase1_write_runtime(state: PipelineState) -> PipelineState:
    """
    Writes Phase-1 artifacts to runtime/runs/<run_id>/...
    """
    run_id = state["run_id"]
    artifacts = state["artifacts"]

    bundle = ArtifactBundle(run_id=run_id, artifacts=artifacts)

    runtime_root = Path("./runtime").resolve()
    run_dir = write_artifacts_to_run_dir(bundle=bundle, runtime_root=runtime_root, overwrite=False)

    state["run_dir"] = str(run_dir)
    return state


def node_generate_test_cases(state: PipelineState) -> PipelineState:
    """
    Uses CIR + Coverage (and Ambiguity if present) to generate TestCases.json (via LLM).
    """
    llm = state["llm"]
    prompt_template = state["prompt_testcases"]
    artifacts = state["artifacts"]

    cir_dict = artifacts["CanonicalUserStoryCIR.json"]
    coverage_dict = artifacts["CoverageIntent.json"]
    ambiguity_dict = artifacts.get("AmbiguityReport.json")  # optional, but usually present

    # Build CanonicalUserStoryCIR Pydantic model (so we validate shape early)
    from contracts.cir_schema import CanonicalUserStoryCIR
    cir = CanonicalUserStoryCIR(**cir_dict)

    # Minimal LLM adapter expected by designer.py
    class _LLMAdapter:
        def __init__(self, inner: Any):
            self.inner = inner

        def generate(self, prompt: str) -> str:
            resp = self.inner.invoke(prompt)
            if isinstance(resp, str):
                return resp
            return getattr(resp, "content", None) or str(resp)

    suite = design_test_cases(
        cir=cir,
        coverage_intent=coverage_dict,
        ambiguity_report=ambiguity_dict,
        llm_client=_LLMAdapter(llm),
        prompt_template=prompt_template,
        config=TestCaseDesignConfig(use_llm=True, temperature_hint=0.1),
    )

    # Store as plain JSON object for writing
    state["test_cases_obj"] = suite.model_dump()
    return state


def node_write_test_cases(state: PipelineState) -> PipelineState:
    """
    Writes TestCases.json into the same runtime run folder.
    """
    run_dir = Path(state["run_dir"]).resolve()
    out_path = run_dir / "TestCases.json"

    obj = state["test_cases_obj"]
    text = json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True)
    out_path.write_text(text + "\n", encoding="utf-8")

    # Also update RunManifest inventory (optional but useful)
    manifest_path = run_dir / "RunManifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            inv = manifest.get("file_inventory", [])
            if "TestCases.json" not in inv:
                inv.append("TestCases.json")
                manifest["file_inventory"] = sorted(inv)
                manifest_path.write_text(
                    json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        except Exception:
            # Don't fail run on manifest update; keep deterministic core flow
            pass

    return state
-----

src/pipeline/graph.py
from __future__ import annotations

from langgraph.graph import StateGraph, END

from pipeline.state import PipelineState
from pipeline.nodes import (
    node_phase1_generate,
    node_phase1_write_runtime,
    node_generate_test_cases,
    node_write_test_cases,
)


def build_graph() -> StateGraph:
    """
    Minimal linear graph:
    Story -> Phase1 LLM -> parse -> write -> Testcases LLM -> write -> END
    """
    g = StateGraph(PipelineState)

    g.add_node("phase1_generate", node_phase1_generate)
    g.add_node("phase1_write_runtime", node_phase1_write_runtime)
    g.add_node("generate_test_cases", node_generate_test_cases)
    g.add_node("write_test_cases", node_write_test_cases)

    g.set_entry_point("phase1_generate")
    g.add_edge("phase1_generate", "phase1_write_runtime")
    g.add_edge("phase1_write_runtime", "generate_test_cases")
    g.add_edge("generate_test_cases", "write_test_cases")
    g.add_edge("write_test_cases", END)

    return g
----


src/main.py
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from ingestion.story_loader import load_user_stories
from pipeline.graph import build_graph


def _read_prompt_file(path: str | Path) -> str:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"Prompt file not found: {p}")
    return p.read_text(encoding="utf-8").strip() + "\n"


def main() -> None:
    load_dotenv()

    story_dir = os.getenv("USER_STORY_DIR", "./user_story")
    runtime_root = os.getenv("RUNTIME_ROOT", "./runtime")

    # Prompts (you said you stored these as .txt files under src/prompts/)
    prompt_phase1_path = os.getenv("PROMPT_PHASE1_PATH", "./src/prompts/phase1_runtime_artifacts.prompt.txt")
    prompt_testcases_path = os.getenv("PROMPT_TESTCASES_PATH", "./src/prompts/test_case_generation.prompt.txt")

    prompt_phase1 = _read_prompt_file(prompt_phase1_path)
    prompt_testcases = _read_prompt_file(prompt_testcases_path)

    # Load stories from directory (temporary local ingestion)
    stories = load_user_stories(story_dir)
    if not stories:
        raise SystemExit(f"No user stories found in: {story_dir}")

    # Pick the first story deterministically for now
    story = stories[0]
    print(f"[main] Selected story: {story.filename}")

    # ---- Azure OpenAI LLM ----
    # You said you already have: llm = get_llm(token)
    # and can do: llm.invoke("what is prime number")
    #
    # IMPORTANT: Update this import path to wherever your get_llm(token) lives.
    #
    # Example token env var names — adjust to your setup:
    token = os.getenv("AZURE_OPENAI_TOKEN") or os.getenv("AZURE_OPENAI_API_KEY") or ""
    if not token:
        print("[main] WARNING: AZURE_OPENAI_TOKEN/AZURE_OPENAI_API_KEY is empty. LLM calls will fail.")

    # CHANGE THIS IMPORT TO YOUR ACTUAL MODULE PATH:
    from your_azure_module import get_llm  # <-- TODO: replace

    llm = get_llm(token)

    # Build + run graph
    graph = build_graph().compile()

    initial_state = {
        "story_id": story.story_id,
        "story_filename": story.filename,
        "story_text": story.raw_text,
        "prompt_phase1": prompt_phase1,
        "prompt_testcases": prompt_testcases,
        "llm": llm,
        "warnings": [],
    }

    # Ensure runtime root exists
    Path(runtime_root).mkdir(parents=True, exist_ok=True)

    final_state = graph.invoke(initial_state)

    print(f"[main] run_id: {final_state.get('run_id')}")
    print(f"[main] run_dir: {final_state.get('run_dir')}")
    if final_state.get("warnings"):
        print("[main] warnings:")
        for w in final_state["warnings"]:
            print(f"  - {w}")


if __name__ == "__main__":
    main()




------

.env

PROMPT_PHASE1_PATH=./src/prompts/phase1_runtime_artifacts.prompt.txt
PROMPT_TESTCASES_PATH=./src/prompts/test_case_generation.prompt.txt
AZURE_OPENAI_TOKEN=...
USER_STORY_DIR=./user_story
RUNTIME_ROOT=./runtime
