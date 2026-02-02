# src/pipeline/graph.py
from __future__ import annotations

from typing import Literal

from langgraph.graph import StateGraph, END

from .state import PipelineState
from . import nodes as n


def _route_test_data_mode(state: PipelineState) -> Literal["ingest_user_test_data", "generate_test_data"]:
    """
    Decide whether to ingest user-provided test data or generate new test data.

    Expected state fields:
      - data_mode: "provided" | "generate" (default: "generate")
    """
    mode = (state.get("data_mode") or "generate").strip().lower()
    if mode == "provided":
        return "ingest_user_test_data"
    return "generate_test_data"


def build_graph() -> StateGraph:
    """
    Full pipeline (single-story run) — FIXED ORDER (stable + consistent with your prompts):

    1) Phase-1 (LLM): produce artifacts (Raw, Ambiguity, CIR, Coverage, Manifest, Delta)
    2) Persist phase-1 artifacts to runtime
    3) Generate TestCases.json using CIR + Coverage + (optional) Ambiguity
       Persist TestCases.json
    4) Test data path (depends on TestCases):
        - data_mode == "provided": ingest user .json/.xlsx → normalized TestData.json
        - else: generate TestData.json via LLM (uses CIR + Coverage + TestCases + optional Ambiguity)
       Persist TestData.json
    5) Generate Gherkin .feature files using CIR + TestCases.json + TestData.json
       Persist .feature files
    """
    g = StateGraph(PipelineState)

    # -----------------------------
    # Phase-1
    # -----------------------------
    g.add_node("generate_phase1", n.node_generate_phase1)
    g.add_node("write_phase1", n.node_write_phase1)

    # -----------------------------
    # Test cases (must come before test data in your design)
    # -----------------------------
    g.add_node("generate_test_cases", n.node_generate_test_cases)
    g.add_node("write_test_cases", n.node_write_test_cases)

    # -----------------------------
    # Test data (branch)
    # -----------------------------
    g.add_node("ingest_user_test_data", n.node_ingest_user_test_data)
    g.add_node("generate_test_data", n.node_generate_test_data)
    g.add_node("write_test_data", n.node_write_test_data)

    # -----------------------------
    # Gherkin
    # -----------------------------
    g.add_node("generate_gherkin", n.node_generate_gherkin)
    g.add_node("write_gherkin", n.node_write_gherkin)

    # -----------------------------
    # Edges (FIXED ORDER)
    # -----------------------------
    g.set_entry_point("generate_phase1")
    g.add_edge("generate_phase1", "write_phase1")

    # ✅ After phase-1, generate test cases first
    g.add_edge("write_phase1", "generate_test_cases")
    g.add_edge("generate_test_cases", "write_test_cases")

    # ✅ Then decide test data mode (provided vs generated)
    g.add_conditional_edges(
        "write_test_cases",
        _route_test_data_mode,
        {
            "ingest_user_test_data": "ingest_user_test_data",
            "generate_test_data": "generate_test_data",
        },
    )

    # Both paths converge to write_test_data
    g.add_edge("ingest_user_test_data", "write_test_data")
    g.add_edge("generate_test_data", "write_test_data")

    # ✅ Then generate gherkin (needs TestCases + TestData)
    g.add_edge("write_test_data", "generate_gherkin")
    g.add_edge("generate_gherkin", "write_gherkin")

    g.add_edge("write_gherkin", END)

    return g
