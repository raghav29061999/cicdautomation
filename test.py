# src/gherkin_design/__init__.py
"""
Gherkin Design (T3)

Responsible for:
- Generating Gherkin feature files from TestCases + TestData (+ optional CIR context)
- Validating basic Gherkin structure (Feature / Scenario presence)
- Writing outputs to runtime/runs/<run_id>/gherkin/*.feature

This module is intentionally tool-agnostic (Cucumber/Behave/SpecFlow later).
"""

----------------------

# src/gherkin_design/gherkin_schema.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List


class GherkinValidationError(Exception):
    """Raised when generated Gherkin does not meet minimum validity rules."""


@dataclass(frozen=True)
class GherkinFile:
    """
    Represents a single .feature file payload.
    """
    filename: str
    content: str


def validate_gherkin_minimal(content: str) -> None:
    """
    Minimal structural validation for Gherkin feature text.

    We keep this intentionally light:
    - Must contain 'Feature:'
    - Must contain at least one 'Scenario:' or 'Scenario Outline:'
    """
    text = (content or "").strip()
    if not text:
        raise GherkinValidationError("Empty Gherkin content.")

    if "Feature:" not in text:
        raise GherkinValidationError("Missing 'Feature:' header in Gherkin content.")

    if ("Scenario:" not in text) and ("Scenario Outline:" not in text):
        raise GherkinValidationError("No 'Scenario:' or 'Scenario Outline:' found in Gherkin content.")


def validate_files(files: List[GherkinFile]) -> None:
    """
    Validate a batch of Gherkin files.
    """
    if not files:
        raise GherkinValidationError("No Gherkin files produced.")

    for f in files:
        if not f.filename.endswith(".feature"):
            raise GherkinValidationError(f"Invalid filename (must end with .feature): {f.filename}")
        validate_gherkin_minimal(f.content)



-------




# src/gherkin_design/generator.py
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .gherkin_schema import GherkinFile, validate_files, GherkinValidationError


class GherkinGenerationError(Exception):
    """Raised when Gherkin generation fails (LLM output/parse/validation)."""


def _coerce_llm_response_to_text(resp: Any) -> str:
    """
    Normalize common LLM return types:
    - LangChain AIMessage => .content
    - plain string
    - dict-like payload
    """
    if isinstance(resp, str):
        return resp

    content = getattr(resp, "content", None)
    if isinstance(content, str):
        return content

    if isinstance(resp, dict):
        for k in ("content", "text", "message"):
            v = resp.get(k)
            if isinstance(v, str):
                return v
        return json.dumps(resp, ensure_ascii=False)

    return str(resp)


_FILE_HEADER_RE = re.compile(r"^###\s*FILE:\s*(.+\.feature)\s*$", re.IGNORECASE)


def _parse_gherkin_files(output_text: str) -> List[GherkinFile]:
    """
    Parse LLM output into one or many GherkinFile objects.

    Supported formats:
    1) Multi-file format (recommended):
       ### FILE: feature_01.feature
       <gherkin...>
       ### FILE: feature_02.feature
       <gherkin...>

    2) Single-file raw gherkin:
       Feature: ...
       Scenario: ...
    """
    text = (output_text or "").strip()
    if not text:
        raise GherkinGenerationError("LLM returned empty output for Gherkin.")

    lines = text.splitlines()
    files: List[GherkinFile] = []

    current_name: Optional[str] = None
    current_buf: List[str] = []

    def flush():
        nonlocal current_name, current_buf
        if current_name and current_buf:
            content = "\n".join(current_buf).strip() + "\n"
            files.append(GherkinFile(filename=current_name, content=content))
        current_name = None
        current_buf = []

    saw_header = False

    for line in lines:
        m = _FILE_HEADER_RE.match(line.strip())
        if m:
            saw_header = True
            flush()
            current_name = m.group(1).strip()
            continue
        current_buf.append(line)

    if saw_header:
        flush()
        if not files:
            raise GherkinGenerationError("Found file headers but produced no file contents.")
        return files

    # No file headers => treat as single feature file
    return [GherkinFile(filename="feature_01.feature", content=text.strip() + "\n")]


class GherkinGenerator:
    """
    Generates Gherkin feature files (text) from CIR + TestCases + TestData.

    Contract:
    - returns a list of GherkinFile objects
    - validates minimal Gherkin structure
    """

    def __init__(self, llm: Any):
        self.llm = llm

    def generate(
        self,
        prompt_text: str,
        cir: Dict[str, Any],
        test_cases: Dict[str, Any],
        test_data: Dict[str, Any],
        control: Dict[str, Any],
    ) -> List[GherkinFile]:
        """
        Generate gherkin feature files.

        control example:
          {
            "strategy": "max_coverage" | "limit",
            "max_scenarios": 5,
            "base_url": "https://www.amazon.com"   # optional override
          }
        """
        if not isinstance(control, dict):
            raise GherkinGenerationError("control must be a dict.")

        # stable serialization to keep determinism high
        cir_s = json.dumps(cir, indent=2, ensure_ascii=False, sort_keys=True)
        tc_s = json.dumps(test_cases, indent=2, ensure_ascii=False, sort_keys=True)
        td_s = json.dumps(test_data, indent=2, ensure_ascii=False, sort_keys=True)
        control_s = json.dumps(control, indent=2, ensure_ascii=False, sort_keys=True)

        rendered = (
            prompt_text.replace("#### File name : CanonicalUserStoryCIR.json\n<PASTE CONTENT>", f"#### File name : CanonicalUserStoryCIR.json\n{cir_s}")
            .replace("#### File name : TestCases.json\n<PASTE CONTENT>", f"#### File name : TestCases.json\n{tc_s}")
            .replace("#### File name : TestData.json\n<PASTE CONTENT>", f"#### File name : TestData.json\n{td_s}")
        )

        # If the prompt expects a control section, inject it. If not, append it.
        if "#### Generation Control" in rendered:
            rendered = rendered.replace(
                "#### Generation Control\n{...}",
                f"#### Generation Control\n{control_s}",
            )
        else:
            rendered = rendered + "\n\n#### Generation Control\n" + control_s + "\n"

        # Call LLM
        resp = self.llm.invoke(rendered)
        raw_text = _coerce_llm_response_to_text(resp)

        # Parse into one or many .feature files
        files = _parse_gherkin_files(raw_text)

        # Validate minimal gherkin structure
        try:
            validate_files(files)
        except GherkinValidationError as e:
            raise GherkinGenerationError(f"Gherkin validation failed: {e}") from e

        return files



----------



# src/gherkin_design/writer.py
from __future__ import annotations

from pathlib import Path
from typing import List

from .gherkin_schema import GherkinFile


class GherkinWriteError(Exception):
    pass


def write_gherkin_files(run_dir: Path, files: List[GherkinFile]) -> Path:
    """
    Write Gherkin feature files into:
      runtime/runs/<run_id>/gherkin/*.feature

    Returns the gherkin output directory.
    """
    if not isinstance(run_dir, Path):
        run_dir = Path(run_dir)

    out_dir = run_dir / "gherkin"
    out_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        # basic safety
        safe_name = f.filename.replace("..", "").replace("\\", "/").split("/")[-1].strip()
        if not safe_name:
            raise GherkinWriteError("Empty filename for gherkin file.")
        if not safe_name.endswith(".feature"):
            safe_name = safe_name + ".feature"

        path = out_dir / safe_name
        path.write_text(f.content, encoding="utf-8")

    return out_dir


