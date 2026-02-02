# src/pipeline/nodes.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Small helpers (internal)
# -----------------------------

def _as_text(llm_response: Any) -> str:
    """
    Azure OpenAI / LangChain often returns AIMessage.
    We always normalize to plain text.
    """
    if llm_response is None:
        return ""
    if isinstance(llm_response, str):
        return llm_response
    # LangChain AIMessage has .content
    content = getattr(llm_response, "content", None)
    if isinstance(content, str):
        return content
    return str(llm_response)


def _ensure_runtime_root(state: Dict[str, Any]) -> Path:
    runtime_root = Path(state.get("runtime_root") or "./runtime/runs")
    runtime_root.mkdir(parents=True, exist_ok=True)
    return runtime_root


def _ensure_run_dir(state: Dict[str, Any]) -> Path:
    """
    Ensure we have a run_dir. Prefer state["run_dir"] else build from run_id.
    """
    runtime_root = _ensure_runtime_root(state)

    run_id = state.get("run_id")
    run_dir_val = state.get("run_dir")

    if run_dir_val:
        run_dir = Path(run_dir_val)
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    if not run_id:
        # If run_id isn't known yet, we still create a temp-ish directory name
        # and allow phase1 writer to overwrite state with real run_id/run_dir.
        run_dir = runtime_root / "RUN-UNKNOWN"
        run_dir.mkdir(parents=True, exist_ok=True)
        state["run_dir"] = str(run_dir)
        return run_dir

    run_dir = runtime_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state["run_dir"] = str(run_dir)
    return run_dir


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def _require(state: Dict[str, Any], key: str) -> Any:
    if key not in state or state[key] is None:
        raise RuntimeError(f"Missing required state key: '{key}'")
    return state[key]


def _load_from_state_or_file(
    state: Dict[str, Any],
    state_key: str,
    run_dir: Path,
    filename: str,
    required: bool = True,
) -> Optional[Dict[str, Any]]:
    obj = state.get(state_key)
    if obj is not None:
        return obj
    p = run_dir / filename
    if p.exists():
        obj = _read_json(p)
        state[state_key] = obj
        return obj
    if required:
        raise RuntimeError(f"Missing '{state_key}' and file not found: {p}")
    return None


def _load_testcases_obj(state: Dict[str, Any], run_dir: Path) -> Dict[str, Any]:
    # We accept multiple possible keys for safety
    for k in ("test_cases_obj", "test_cases"):
        if state.get(k) is not None:
            return state[k]
    tc_path = run_dir / "TestCases.json"
    if tc_path.exists():
        obj = _read_json(tc_path)
        state["test_cases_obj"] = obj
        return obj
    raise RuntimeError(
        "No test cases available. Expected state['test_cases_obj'] or runtime TestCases.json."
    )


def _split_gherkin_files(raw: str) -> List[Tuple[str, str]]:
    """
    Accept either:
    - single gherkin text (no markers) -> one file
    - multiple files using markers:
        ### FILE: <name>.feature
        <gherkin...>
    """
    raw = raw.strip()
    if "### FILE:" not in raw:
        return [("feature_001.feature", raw)]

    files: List[Tuple[str, str]] = []
    lines = raw.splitlines()
    cur_name: Optional[str] = None
    cur_buf: List[str] = []

    def flush():
        nonlocal cur_name, cur_buf
        if cur_name and cur_buf:
            files.append((cur_name, "\n".join(cur_buf).strip() + "\n"))
        cur_name, cur_buf = None, []

    for ln in lines:
        if ln.strip().startswith("### FILE:"):
            flush()
            cur_name = ln.split("### FILE:", 1)[1].strip()
            if not cur_name.endswith(".feature"):
                cur_name += ".feature"
        else:
            if cur_name is None:
                # If content starts before first marker, ignore until marker
                continue
            cur_buf.append(ln)
    flush()
    return files or [("feature_001.feature", raw + "\n")]


# -----------------------------
# NODE 1: Phase-1 generation
# -----------------------------

def node_phase1_generate(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calls LLM using phase1 prompt and story_text, expects JSON envelope output:
    { "run_id": "...", "artifacts": { ... } }
    """
    llm = _require(state, "llm")
    story_text = _require(state, "story_text")
    prompt_phase1 = _require(state, "prompt_phase1")

    # Build the final prompt
    full_prompt = f"{prompt_phase1}\n\nNOW PROCESS THIS USER STORY:\n\"\"\"{story_text}\"\"\""

    raw = _as_text(llm.invoke(full_prompt))
    try:
        obj = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"Phase1 LLM did not return valid JSON. Error: {e}\nRaw:\n{raw[:2000]}")

    run_id = obj.get("run_id")
    artifacts = obj.get("artifacts")
    if not run_id or not isinstance(artifacts, dict):
        raise RuntimeError("Phase1 output missing required keys: run_id and artifacts.")

    # Store in state for downstream nodes
    state["run_id"] = run_id
    state["phase1_envelope"] = obj
    state["artifacts"] = artifacts

    # Also cache key artifacts in convenient keys
    state["cir_obj"] = artifacts.get("CanonicalUserStoryCIR.json")
    state["coverage_obj"] = artifacts.get("CoverageIntent.json")
    state["ambiguity_obj"] = artifacts.get("AmbiguityReport.json")

    return {
        "run_id": run_id,
        "phase1_envelope": obj,
        "artifacts": artifacts,
        "cir_obj": state.get("cir_obj"),
        "coverage_obj": state.get("coverage_obj"),
        "ambiguity_obj": state.get("ambiguity_obj"),
    }


def node_phase1_write_runtime(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Writes phase-1 artifacts to runtime/<run_id>/...
    """
    run_id = _require(state, "run_id")
    artifacts = _require(state, "artifacts")

    run_dir = _ensure_run_dir(state)
    # If run_dir was RUN-UNKNOWN earlier, fix it now
    runtime_root = _ensure_runtime_root(state)
    correct_run_dir = runtime_root / run_id
    correct_run_dir.mkdir(parents=True, exist_ok=True)
    state["run_dir"] = str(correct_run_dir)
    run_dir = correct_run_dir

    # Write all expected artifacts
    file_map = {
        "RawUserStory.json": "RawUserStory.json",
        "AmbiguityReport.json": "AmbiguityReport.json",
        "CanonicalUserStoryCIR.json": "CanonicalUserStoryCIR.json",
        "CoverageIntent.json": "CoverageIntent.json",
        "RunManifest.json": "RunManifest.json",
        "ContractDeltaSuggestions.md": "ContractDeltaSuggestions.md",
    }

    for key, filename in file_map.items():
        if key not in artifacts:
            # do not crash; warn
            warnings = state.setdefault("warnings", [])
            warnings.append(f"Phase1 artifacts missing key: {key}")
            continue
        out_path = run_dir / filename
        val = artifacts[key]
        if filename.endswith(".md"):
            out_path.write_text(str(val), encoding="utf-8")
        else:
            _write_json(out_path, val)

    return {"run_dir": str(run_dir), "warnings": state.get("warnings", [])}


# -----------------------------
# NODE 2: Test case generation
# -----------------------------

def node_generate_test_cases(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates TestCases.json using CIR + Coverage (+ optional Ambiguity)
    This node MUST NOT require TestData (by design).
    """
    run_dir = _ensure_run_dir(state)
    llm = _require(state, "llm")
    prompt = _require(state, "prompt_testcases")

    cir = _load_from_state_or_file(state, "cir_obj", run_dir, "CanonicalUserStoryCIR.json", required=True)
    cov = _load_from_state_or_file(state, "coverage_obj", run_dir, "CoverageIntent.json", required=True)
    amb = _load_from_state_or_file(state, "ambiguity_obj", run_dir, "AmbiguityReport.json", required=False)

    # Build the prompt as your prompt expects "#### File name : ..."
    parts = [
        prompt,
        "\n#### File name : CanonicalUserStoryCIR.json\n" + json.dumps(cir, indent=2, ensure_ascii=False),
        "\n#### File name : CoverageIntent.json\n" + json.dumps(cov, indent=2, ensure_ascii=False),
    ]
    if amb is not None:
        parts.append("\n#### File name : AmbiguityReport.json\n" + json.dumps(amb, indent=2, ensure_ascii=False))
    full_prompt = "\n".join(parts)

    raw = _as_text(llm.invoke(full_prompt))
    try:
        obj = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"TestCases LLM did not return valid JSON. Error: {e}\nRaw:\n{raw[:2000]}")

    # Validate using your validator if available
    try:
        from src.test_design.validator import validate_test_case_suite
        validate_test_case_suite(obj)
    except ImportError:
        # If validator not present, still proceed
        pass

    state["test_cases_obj"] = obj
    return {"test_cases_obj": obj}


def node_write_test_cases(state: Dict[str, Any]) -> Dict[str, Any]:
    run_dir = _ensure_run_dir(state)
    obj = _require(state, "test_cases_obj")

    out_path = run_dir / "TestCases.json"
    _write_json(out_path, obj)
    state["test_cases_path"] = str(out_path)
    return {"test_cases_path": str(out_path)}


# -----------------------------
# NODE 3: Test data (provided)
# -----------------------------

def node_ingest_user_test_data(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ingest user-provided test data (.json or .xlsx) into a normalized TestData.json object.
    Expected state:
      - provided_testdata_filename
      - provided_testdata_bytes
    """
    run_dir = _ensure_run_dir(state)
    filename = _require(state, "provided_testdata_filename")
    data_bytes = _require(state, "provided_testdata_bytes")

    # Let your user_data module handle this if you created it
    try:
        from src.user_data.loader import load_user_test_data  # you said you created "user_data code"
        obj = load_user_test_data(filename=filename, file_bytes=data_bytes)
    except ImportError:
        # Minimal fallback: accept JSON only
        if filename.lower().endswith(".json"):
            obj = json.loads(data_bytes.decode("utf-8", errors="replace"))
        else:
            raise RuntimeError(
                "User test data ingestion requires src.user_data.loader.load_user_test_data "
                "or provide .json. (xlsx ingestion not available in fallback)."
            )

    # Validate if validator exists
    try:
        from src.test_data_design.validator import validate_test_data_suite
        validate_test_data_suite(obj)
    except ImportError:
        pass

    state["test_data_obj"] = obj
    return {"test_data_obj": obj}


# -----------------------------
# NODE 3B: Test data (generated)
# -----------------------------

def node_generate_test_data(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate TestData.json using CIR + Coverage + TestCases (+ optional Ambiguity)
    """
    run_dir = _ensure_run_dir(state)
    llm = _require(state, "llm")
    prompt = _require(state, "prompt_testdata")

    cir = _load_from_state_or_file(state, "cir_obj", run_dir, "CanonicalUserStoryCIR.json", required=True)
    cov = _load_from_state_or_file(state, "coverage_obj", run_dir, "CoverageIntent.json", required=True)
    amb = _load_from_state_or_file(state, "ambiguity_obj", run_dir, "AmbiguityReport.json", required=False)

    tc = _load_testcases_obj(state, run_dir)

    parts = [
        prompt,
        "\n#### File name : CanonicalUserStoryCIR.json\n" + json.dumps(cir, indent=2, ensure_ascii=False),
        "\n#### File name : CoverageIntent.json\n" + json.dumps(cov, indent=2, ensure_ascii=False),
        "\n#### File name : TestCases.json\n" + json.dumps(tc, indent=2, ensure_ascii=False),
    ]
    if amb is not None:
        parts.append("\n#### File name : AmbiguityReport.json\n" + json.dumps(amb, indent=2, ensure_ascii=False))
    full_prompt = "\n".join(parts)

    raw = _as_text(llm.invoke(full_prompt))
    try:
        obj = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"TestData LLM did not return valid JSON. Error: {e}\nRaw:\n{raw[:2000]}")

    # Validate if available
    try:
        from src.test_data_design.validator import validate_test_data_suite
        validate_test_data_suite(obj)
    except ImportError:
        pass

    state["test_data_obj"] = obj
    return {"test_data_obj": obj}


def node_write_test_data(state: Dict[str, Any]) -> Dict[str, Any]:
    run_dir = _ensure_run_dir(state)
    obj = _require(state, "test_data_obj")

    out_path = run_dir / "TestData.json"
    _write_json(out_path, obj)
    state["test_data_path"] = str(out_path)
    return {"test_data_path": str(out_path)}


# -----------------------------
# NODE 4: Gherkin generation
# -----------------------------

def node_generate_gherkin(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates one or more .feature files content (not written yet).
    Prompt should ideally output multiple files using ### FILE: markers,
    but we accept a single output too.
    """
    run_dir = _ensure_run_dir(state)
    llm = _require(state, "llm")
    prompt = _require(state, "prompt_gherkin")

    cir = _load_from_state_or_file(state, "cir_obj", run_dir, "CanonicalUserStoryCIR.json", required=True)
    tc = _load_testcases_obj(state, run_dir)
    td = _load_from_state_or_file(state, "test_data_obj", run_dir, "TestData.json", required=True)

    strategy = state.get("gherkin_strategy") or "limit"
    max_files = state.get("gherkin_max_files")
    try:
        max_files_int = int(max_files) if max_files is not None else 5
    except Exception:
        max_files_int = 5

    control = {
        "strategy": "max_coverage" if max_files_int == 0 else "limit",
        "max_scenarios": None if max_files_int == 0 else max_files_int,
    }

    parts = [
        prompt,
        "\n#### File name : CanonicalUserStoryCIR.json\n" + json.dumps(cir, indent=2, ensure_ascii=False),
        "\n#### File name : TestCases.json\n" + json.dumps(tc, indent=2, ensure_ascii=False),
        "\n#### File name : TestData.json\n" + json.dumps(td, indent=2, ensure_ascii=False),
        "\n#### Generation Control\n" + json.dumps(control, indent=2, ensure_ascii=False),
    ]
    full_prompt = "\n".join(parts)

    raw = _as_text(llm.invoke(full_prompt))
    files = _split_gherkin_files(raw)

    state["gherkin_files"] = files  # list[(filename, content)]
    return {"gherkin_files": files}


def node_write_gherkin(state: Dict[str, Any]) -> Dict[str, Any]:
    run_dir = _ensure_run_dir(state)
    files: List[Tuple[str, str]] = _require(state, "gherkin_files")

    out_dir = run_dir / "gherkin"
    out_dir.mkdir(parents=True, exist_ok=True)

    written: List[str] = []
    for i, (name, content) in enumerate(files, start=1):
        safe_name = name.strip() or f"feature_{i:03d}.feature"
        p = out_dir / safe_name
        p.write_text(content, encoding="utf-8")
        written.append(str(p))

    state["gherkin_dir"] = str(out_dir)
    return {"gherkin_dir": str(out_dir), "gherkin_written": written}
