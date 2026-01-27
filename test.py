# src/gherkin_design/__init__.py
"""
Gherkin Design (T3)

Consumes:
- CanonicalUserStoryCIR.json (context)
- TestCases.json
- TestData.json

Produces:
- One or more .feature files under runtime/runs/<run_id>/gherkin/

This layer is intentionally tool-agnostic (Cucumber/Behave integration comes later).
"""

------------------------------------------------------------
# src/gherkin_design/gherkin_schema.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class GherkinGenerationControl:
    """
    Controls how many scenarios/features are generated.

    strategy:
      - "max_coverage": generate as many scenarios as needed to cover test cases
      - "limit": generate up to max_scenarios (highest value/risk first)

    max_scenarios:
      - used only when strategy == "limit"
    """
    strategy: str = "max_coverage"
    max_scenarios: int | None = None


@dataclass(frozen=True)
class GherkinFeatureFile:
    """
    A single .feature file payload.
    """
    filename: str
    content: str


def validate_control(control: GherkinGenerationControl) -> None:
    if control.strategy not in ("max_coverage", "limit"):
        raise ValueError("control.strategy must be 'max_coverage' or 'limit'")

    if control.strategy == "limit":
        if control.max_scenarios is None:
            raise ValueError("control.max_scenarios must be provided when strategy='limit'")
        if control.max_scenarios <= 0:
            raise ValueError("control.max_scenarios must be > 0")

--------------------------------

# src/gherkin_design/generator.py
from __future__ import annotations

import re
from typing import Any, Dict, List

from .gherkin_schema import (
    GherkinFeatureFile,
    GherkinGenerationControl,
    validate_control,
)


class GherkinGenerationError(Exception):
    """Raised when gherkin generation fails."""


def _coerce_llm_response_to_text(resp: Any) -> str:
    """
    Normalize common LLM client return types to plain text.
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
        return str(resp)
    return str(resp)


def _extract_gherkin_text(text: str) -> str:
    """
    Best-effort extraction of Gherkin from noisy output.
    We look for the first 'Feature:' line and take everything after it.
    """
    s = text.replace("\r\n", "\n").strip()
    m = re.search(r"(?m)^\s*Feature\s*:\s*.+$", s)
    if not m:
        raise GherkinGenerationError("No 'Feature:' section found in LLM output.")
    return s[m.start():].strip() + "\n"


def _split_into_features(gherkin_text: str) -> List[GherkinFeatureFile]:
    """
    Split a single text blob into multiple .feature files if it contains
    multiple 'Feature:' blocks.
    """
    blocks = re.split(r"(?m)^(?=\s*Feature\s*:)", gherkin_text)
    blocks = [b.strip() for b in blocks if b.strip()]

    out: List[GherkinFeatureFile] = []
    for i, b in enumerate(blocks, start=1):
        filename = f"feature_{i:02d}.feature"
        out.append(GherkinFeatureFile(filename=filename, content=b.strip() + "\n"))
    return out


class GherkinGenerator:
    """
    Generates Gherkin .feature files (text) from TestCases + TestData (+ CIR context).
    """

    def __init__(self, llm: Any):
        self.llm = llm

    def generate(
        self,
        prompt_text: str,
        cir: Dict[str, Any],
        test_cases: Dict[str, Any],
        test_data: Dict[str, Any],
        control: GherkinGenerationControl,
    ) -> List[GherkinFeatureFile]:
        validate_control(control)

        control_payload = {
            "strategy": control.strategy,
            "max_scenarios": control.max_scenarios,
        }

        rendered_prompt = (
            prompt_text
            .replace("#### File name : CanonicalUserStoryCIR.json\n<PASTE CONTENT>", f"#### File name : CanonicalUserStoryCIR.json\n{_json(cir)}")
            .replace("#### File name : TestCases.json\n<PASTE CONTENT>", f"#### File name : TestCases.json\n{_json(test_cases)}")
            .replace("#### File name : TestData.json\n<PASTE CONTENT>", f"#### File name : TestData.json\n{_json(test_data)}")
            .replace("#### Generation Control\n{\n  \"strategy\": \"max_coverage | limit\",\n  \"max_scenarios\": <integer or null>\n}", f"#### Generation Control\n{_json(control_payload)}")
        )

        resp = self.llm.invoke(rendered_prompt)
        raw_text = _coerce_llm_response_to_text(resp)

        gherkin_text = _extract_gherkin_text(raw_text)
        files = _split_into_features(gherkin_text)

        # Minimal sanity: every file should start with Feature:
        for f in files:
            if not f.content.lstrip().startswith("Feature:"):
                raise GherkinGenerationError("Generated feature file does not start with 'Feature:'")

        return files


def _json(obj: Any) -> str:
    import json
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True)
-------------------------------------------------------------------
# src/gherkin_design/writer.py
from __future__ import annotations

from pathlib import Path
from typing import List

from .gherkin_schema import GherkinFeatureFile


def write_gherkin_files(run_dir: Path, files: List[GherkinFeatureFile]) -> Path:
    """
    Writes Gherkin .feature files under runtime/runs/<run_id>/gherkin/
    Returns the gherkin directory path.
    """
    gherkin_dir = run_dir / "gherkin"
    gherkin_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        path = gherkin_dir / f.filename
        path.write_text(f.content, encoding="utf-8")

    return gherkin_dir

