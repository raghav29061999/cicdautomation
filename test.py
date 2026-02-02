# src/pipeline/graph.py
from __future__ import annotations

from typing import Literal, Callable, Any, Dict

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
    Full pipeline (single-story run):

    1) Phase-1 (LLM): produce artifacts (Raw, Ambiguity, CIR, Coverage, Manifest, Delta)
    2) Persist phase-1 artifacts to runtime
    3) Test data path:
        - data_mode == "provided": ingest user .json/.xlsx → normalized TestData.json
        - else: generate TestData.json via LLM
       Persist TestData.json
    4) Generate TestCases.json using CIR + Coverage + (optional) Ambiguity + TestData.json
       Persist TestCases.json
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
    # Test data (branch)
    # -----------------------------
    g.add_node("ingest_user_test_data", n.node_ingest_user_test_data)  # NEW
    g.add_node("generate_test_data", n.node_generate_test_data)        # existing
    g.add_node("write_test_data", n.node_write_test_data)              # existing

    # -----------------------------
    # Test cases
    # -----------------------------
    g.add_node("generate_test_cases", n.node_generate_test_cases)      # existing
    g.add_node("write_test_cases", n.node_write_test_cases)            # existing (if you have it)

    # -----------------------------
    # Gherkin
    # -----------------------------
    g.add_node("generate_gherkin", n.node_generate_gherkin)            # existing/new
    g.add_node("write_gherkin", n.node_write_gherkin)                  # existing/new

    # -----------------------------
    # Edges
    # -----------------------------
    g.set_entry_point("generate_phase1")
    g.add_edge("generate_phase1", "write_phase1")

    # Conditional: data ingest vs data generate
    g.add_conditional_edges(
        "write_phase1",
        _route_test_data_mode,
        {
            "ingest_user_test_data": "ingest_user_test_data",
            "generate_test_data": "generate_test_data",
        },
    )

    # Both paths converge to write_test_data
    g.add_edge("ingest_user_test_data", "write_test_data")
    g.add_edge("generate_test_data", "write_test_data")

    # After TestData.json exists, generate tests (grounded by TestData)
    g.add_edge("write_test_data", "generate_test_cases")
    g.add_edge("generate_test_cases", "write_test_cases")

    # Then gherkin
    g.add_edge("write_test_cases", "generate_gherkin")
    g.add_edge("generate_gherkin", "write_gherkin")

    g.add_edge("write_gherkin", END)

    return g
