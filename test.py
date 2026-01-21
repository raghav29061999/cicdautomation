# src/test_data_design/generator.py
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .test_data_schema import TestDataSuite


class TestDataGenerationError(Exception):
    """Raised when test data generation fails (parse/contract issues)."""


def _coerce_llm_response_to_text(resp: Any) -> str:
    """
    Normalize common LLM client return types to plain text.
    - LangChain often returns AIMessage with .content
    - Some clients return dict-like payloads
    - Some return plain strings
    """
    if isinstance(resp, str):
        return resp

    content = getattr(resp, "content", None)
    if isinstance(content, str):
        return content

    # Dict-like fallback (some SDKs)
    if isinstance(resp, dict):
        # Try common keys
        for k in ("content", "text", "message"):
            v = resp.get(k)
            if isinstance(v, str):
                return v
        return json.dumps(resp, ensure_ascii=False)

    return str(resp)


def _extract_first_json_object(text: str) -> str:
    """
    Best-effort extraction of the first JSON object from a response that may
    include leading/trailing junk (despite the prompt saying JSON-only).
    This is a safety net for production robustness.
    """
    s = text.strip()
    if s.startswith("{") and s.endswith("}"):
        return s

    start = s.find("{")
    if start == -1:
        raise TestDataGenerationError("No JSON object start '{' found in LLM response.")

    # Scan to find matching closing brace for the first JSON object
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(s)):
        ch = s[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]

    raise TestDataGenerationError("Unbalanced JSON braces; could not extract a full JSON object.")


def _normalize_testdata_obj(obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize common field drifts from LLM output WITHOUT changing meaning.
    This is the permanent guardrail that prevents brittle prompt coupling.

    Current normalizations:
    - linked_test_case -> linked_test_cases (datasets and negative_and_edge_data)
    """
    # datasets[*]
    for ds in obj.get("datasets", []) or []:
        if isinstance(ds, dict) and "linked_test_case" in ds and "linked_test_cases" not in ds:
            ds["linked_test_cases"] = ds.pop("linked_test_case")

    # negative_and_edge_data[*]
    for neg in obj.get("negative_and_edge_data", []) or []:
        if isinstance(neg, dict) and "linked_test_case" in neg and "linked_test_cases" not in neg:
            neg["linked_test_cases"] = neg.pop("linked_test_case")

    return obj


class TestDataGenerator:
    """
    Generates TestData.json using LLM output.

    Design goals:
    - Works with LangChain-style AIMessage responses
    - Recovers from minor prompt drift (field naming)
    - Enforces schema via Pydantic (TestDataSuite)
    """

    def __init__(self, llm: Any):
        self.llm = llm

    def generate(
        self,
        prompt_text: str,
        cir: Dict[str, Any],
        coverage: Dict[str, Any],
        test_cases: Dict[str, Any],
        ambiguity: Optional[Dict[str, Any]] = None,
    ) -> TestDataSuite:
        """
        Generate and validate TestDataSuite.
        """
        # Keep injection deterministic: serialize inputs consistently
        cir_s = json.dumps(cir, indent=2, ensure_ascii=False, sort_keys=True)
        cov_s = json.dumps(coverage, indent=2, ensure_ascii=False, sort_keys=True)
        tc_s = json.dumps(test_cases, indent=2, ensure_ascii=False, sort_keys=True)
        amb_s = json.dumps(ambiguity, indent=2, ensure_ascii=False, sort_keys=True) if ambiguity else ""

        rendered_prompt = (
            prompt_text.replace("#### File name : CanonicalUserStoryCIR.json\n<PASTE CONTENT>", f"#### File name : CanonicalUserStoryCIR.json\n{cir_s}")
            .replace("#### File name : CoverageIntent.json\n<PASTE CONTENT>", f"#### File name : CoverageIntent.json\n{cov_s}")
            .replace("#### File name : TestCases.json\n<PASTE CONTENT>", f"#### File name : TestCases.json\n{tc_s}")
        )

        # Ambiguity block is optional; if the prompt includes the placeholder, fill it
        if "#### File name : AmbiguityReport.json" in rendered_prompt:
            if amb_s:
                rendered_prompt = rendered_prompt.replace(
                    "#### File name : AmbiguityReport.json\n<PASTE CONTENT IF AVAILABLE>",
                    f"#### File name : AmbiguityReport.json\n{amb_s}",
                )
            else:
                # Remove placeholder content but keep header
                rendered_prompt = rendered_prompt.replace(
                    "#### File name : AmbiguityReport.json\n<PASTE CONTENT IF AVAILABLE>",
                    "#### File name : AmbiguityReport.json\n{}",
                )

        # Call LLM
        resp = self.llm.invoke(rendered_prompt)
        raw_text = _coerce_llm_response_to_text(resp)

        # Parse JSON safely
        json_text = _extract_first_json_object(raw_text)

        try:
            obj = json.loads(json_text)
        except json.JSONDecodeError as e:
            raise TestDataGenerationError(f"Invalid JSON from LLM: {e}") from e

        if not isinstance(obj, dict):
            raise TestDataGenerationError("LLM output must be a JSON object at the top-level.")

        obj = _normalize_testdata_obj(obj)

        # Validate schema
        try:
            suite = TestDataSuite(**obj)
        except Exception as e:
            raise TestDataGenerationError(f"TestData schema validation failed: {e}") from e

        return suite
