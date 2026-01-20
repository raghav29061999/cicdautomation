init.py

"""
test_design package

Purpose:
- Define the static contract for generated Test Cases
- Provide deterministic transformation: CIR (+ Coverage + Ambiguity) -> TestCases
- Validate generated TestCases with governance rules

This package does NOT execute tests or generate scripts/data.
"""
-----------

src/test_design/test_case_schema.py



from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class TestType(str, Enum):
    positive = "positive"
    negative = "negative"
    edge = "edge"
    regression = "regression"
    nfr = "nfr"


class Priority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    tbd = "TBD"


class TestStep(BaseModel):
    """
    A single test step.

    - action: what to do (user/system)
    - inputs: structured key/value inputs for determinism (avoid prose blobs)
    - expected_result: what must be observed after this step
    """
    model_config = ConfigDict(extra="forbid")

    action: str = Field(..., min_length=1, description="High-level action.")
    inputs: Dict[str, str] = Field(default_factory=dict, description="Structured inputs.")
    expected_result: str = Field(..., min_length=1, description="Expected result after step.")


class TestCase(BaseModel):
    """
    Canonical Test Case object produced by the system.

    This is intentionally framework-agnostic and stable across stories.
    """
    model_config = ConfigDict(extra="forbid")

    test_case_id: str = Field(..., description="Stable ID within a run (e.g., TC-001).")
    title: str = Field(..., min_length=1)
    test_type: TestType

    linked_acceptance_criteria: List[str] = Field(
        default_factory=list,
        description="Acceptance criteria IDs covered by this test case.",
    )

    preconditions: List[str] = Field(default_factory=list)
    steps: List[TestStep] = Field(..., min_length=1)
    expected_final_outcome: str = Field(..., min_length=1)

    priority: Priority = Field(default=Priority.tbd)
    notes: List[str] = Field(default_factory=list)


class TestCaseSuite(BaseModel):
    """
    Container for all test cases produced for a given run_id.

    This is what you'll persist as TestCases.json later.
    """
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., min_length=3)
    test_cases: List[TestCase] = Field(default_factory=list)
------------------

src/test_design/validator.py




from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set

from pydantic import BaseModel, Field, ConfigDict

from test_design.test_case_schema import TestCaseSuite, TestCase, TestType


class TestCaseValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: str  # low|medium|high
    location: str
    message: str
    suggested_fix: str = "TBD"


class TestCaseValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    errors: List[TestCaseValidationIssue] = Field(default_factory=list)
    warnings: List[TestCaseValidationIssue] = Field(default_factory=list)

    def add_error(self, issue: TestCaseValidationIssue) -> None:
        self.errors.append(issue)

    def add_warning(self, issue: TestCaseValidationIssue) -> None:
        self.warnings.append(issue)


@dataclass(frozen=True)
class TestCaseValidationPolicy:
    """
    Governance for test cases.

    Keep it deterministic and generic:
    - Link to ACs must exist
    - IDs must be unique
    - Steps must not be empty
    """
    require_ac_links: bool = True
    max_steps_per_test: int = 20
    min_steps_per_test: int = 1
    allow_empty_preconditions: bool = True


DEFAULT_POLICY = TestCaseValidationPolicy()


def validate_test_case_suite(
    suite: TestCaseSuite,
    known_acceptance_criteria_ids: Set[str],
    policy: TestCaseValidationPolicy = DEFAULT_POLICY,
) -> TestCaseValidationReport:
    report = TestCaseValidationReport(is_valid=True)

    # Unique test_case_id
    seen_ids: Set[str] = set()
    for i, tc in enumerate(suite.test_cases):
        loc = f"test_cases[{i}]"

        if tc.test_case_id in seen_ids:
            report.add_error(
                TestCaseValidationIssue(
                    code="TC-VAL-001",
                    severity="high",
                    location=f"{loc}.test_case_id",
                    message=f"Duplicate test_case_id: {tc.test_case_id}",
                    suggested_fix="Ensure TC IDs are unique and sequential within the suite.",
                )
            )
        else:
            seen_ids.add(tc.test_case_id)

        # Must have steps
        if len(tc.steps) < policy.min_steps_per_test:
            report.add_error(
                TestCaseValidationIssue(
                    code="TC-VAL-002",
                    severity="high",
                    location=f"{loc}.steps",
                    message="Test case must contain at least one step.",
                    suggested_fix="Add at least one actionable step with expected result.",
                )
            )

        if len(tc.steps) > policy.max_steps_per_test:
            report.add_warning(
                TestCaseValidationIssue(
                    code="TC-VAL-003",
                    severity="medium",
                    location=f"{loc}.steps",
                    message=f"Test case has many steps ({len(tc.steps)}). May be too verbose.",
                    suggested_fix="Consider splitting into smaller tests if steps represent distinct behaviors.",
                )
            )

        # AC link checks
        if policy.require_ac_links:
            if not tc.linked_acceptance_criteria:
                report.add_error(
                    TestCaseValidationIssue(
                        code="TC-VAL-004",
                        severity="high",
                        location=f"{loc}.linked_acceptance_criteria",
                        message="Test case must link to at least one acceptance criterion.",
                        suggested_fix="Link the test to at least one AC ID from the CIR.",
                    )
                )
            else:
                unknown = [ac for ac in tc.linked_acceptance_criteria if ac not in known_acceptance_criteria_ids]
                if unknown:
                    report.add_error(
                        TestCaseValidationIssue(
                            code="TC-VAL-005",
                            severity="high",
                            location=f"{loc}.linked_acceptance_criteria",
                            message=f"Test case links to unknown AC IDs: {unknown}",
                            suggested_fix="Use only AC IDs present in the CIR functional_requirements.",
                        )
                    )

        # NFR tests should link to some AC or be explicitly justified
        if tc.test_type == TestType.nfr and not tc.notes:
            report.add_warning(
                TestCaseValidationIssue(
                    code="TC-VAL-006",
                    severity="low",
                    location=f"{loc}.notes",
                    message="NFR test case has no notes; rationale may be unclear.",
                    suggested_fix="Add a short note describing why this NFR test is needed and how it will be validated.",
                )
            )

    if report.errors:
        report.is_valid = False
    return report





-----------------------


src/test_design/designer.py

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Set, List, Protocol

from pydantic import ValidationError as PydanticValidationError

from contracts.cir_schema import CanonicalUserStoryCIR
from contracts.validation_spec import validate_cir
from test_design.test_case_schema import TestCaseSuite, TestCase
from test_design.validator import validate_test_case_suite, TestCaseValidationPolicy, DEFAULT_POLICY


class LLMClient(Protocol):
    """
    Minimal interface you can implement later with OpenAI / Azure / Gemini etc.
    """
    def generate(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class TestCaseDesignConfig:
    """
    Configuration for test case design step.
    """
    use_llm: bool = False
    temperature_hint: float = 0.1
    policy: TestCaseValidationPolicy = DEFAULT_POLICY


class TestCaseDesignError(Exception):
    pass


def design_test_cases(
    cir: CanonicalUserStoryCIR,
    coverage_intent: dict,
    ambiguity_report: Optional[dict] = None,
    llm_client: Optional[LLMClient] = None,
    prompt_template: Optional[str] = None,
    config: TestCaseDesignConfig = TestCaseDesignConfig(),
) -> TestCaseSuite:
    """
    Deterministic boundary: CIR (+ Coverage + Ambiguity) -> TestCaseSuite

    - Validates CIR first (hard gate)
    - If config.use_llm is False, returns an empty suite (placeholder)
    - If config.use_llm is True, calls the LLM and parses JSON into TestCaseSuite
    - Validates test cases against governance rules (hard gate)
    """
    # 1) CIR governance validation
    cir_report = validate_cir(cir)
    if not cir_report.is_valid:
        raise TestCaseDesignError(
            "CIR validation failed; cannot design test cases. "
            f"Errors: {[e.model_dump() for e in cir_report.errors]}"
        )

    # Derive known AC IDs for downstream validation
    known_ac_ids: Set[str] = set()
    for ac in cir.functional_requirements:
        if ac.ac_id:
            known_ac_ids.add(ac.ac_id)

    # 2) Placeholder mode (no LLM yet)
    if not config.use_llm:
        suite = TestCaseSuite(run_id=cir.run_id, test_cases=[])
        return suite

    # 3) LLM mode
    if llm_client is None:
        raise TestCaseDesignError("LLM mode enabled but llm_client is None.")
    if not prompt_template:
        raise TestCaseDesignError("LLM mode enabled but prompt_template is None.")

    prompt = _render_test_case_prompt(
        prompt_template=prompt_template,
        cir=cir,
        coverage_intent=coverage_intent,
        ambiguity_report=ambiguity_report,
    )

    raw = llm_client.generate(prompt)
    suite = _parse_test_case_output(raw, expected_run_id=cir.run_id)

    # 4) Governance validation for test cases
    tc_report = validate_test_case_suite(suite, known_acceptance_criteria_ids=known_ac_ids, policy=config.policy)
    if not tc_report.is_valid:
        raise TestCaseDesignError(
            "Generated test cases failed validation. "
            f"Errors: {[e.model_dump() for e in tc_report.errors]}"
        )

    return suite


def _render_test_case_prompt(
    prompt_template: str,
    cir: CanonicalUserStoryCIR,
    coverage_intent: dict,
    ambiguity_report: Optional[dict],
) -> str:
    """
    Render the prompt by appending inputs in a consistent way.

    We keep it simple: template + appended JSON blocks.
    This avoids brittle string placeholder substitution.
    """
    parts: List[str] = [prompt_template.strip(), "", "NOW GENERATE TEST CASES USING THESE INPUTS:"]
    parts.append("#### File name : CanonicalUserStoryCIR.json")
    parts.append(json.dumps(cir.model_dump(), indent=2, sort_keys=True, ensure_ascii=False))
    parts.append("")
    parts.append("#### File name : CoverageIntent.json")
    parts.append(json.dumps(coverage_intent, indent=2, sort_keys=True, ensure_ascii=False))

    if ambiguity_report is not None:
        parts.append("")
        parts.append("#### File name : AmbiguityReport.json")
        parts.append(json.dumps(ambiguity_report, indent=2, sort_keys=True, ensure_ascii=False))

    return "\n".join(parts).strip() + "\n"


def _parse_test_case_output(raw_text: str, expected_run_id: str) -> TestCaseSuite:
    """
    Expects strict JSON output:
    { "run_id": "...", "test_cases": [ ... ] }

    Raises TestCaseDesignError on any parse/validation failure.
    """
    s = raw_text.strip()
    try:
        obj = json.loads(s)
    except json.JSONDecodeError as e:
        raise TestCaseDesignError(f"Invalid JSON returned by LLM: {e}") from e

    if not isinstance(obj, dict):
        raise TestCaseDesignError("LLM output must be a JSON object.")

    if obj.get("run_id") != expected_run_id:
        raise TestCaseDesignError(
            f"run_id mismatch: expected {expected_run_id}, got {obj.get('run_id')}"
        )

    # Validate against Pydantic schema
    try:
        suite = TestCaseSuite(**obj)
    except PydanticValidationError as e:
        raise TestCaseDesignError(f"TestCaseSuite schema validation failed: {e}") from e

    # Ensure TC IDs exist; if not, we can auto-assign deterministically (optional)
    _ensure_tc_ids(suite)
    return suite


def _ensure_tc_ids(suite: TestCaseSuite) -> None:
    """
    Deterministically assign missing TC IDs as TC-001, TC-002, ...
    (Mutates the suite in-memory; persistence will write the final state.)
    """
    changed = False
    for idx, tc in enumerate(suite.test_cases, start=1):
        if not tc.test_case_id or not tc.test_case_id.strip():
            # Pydantic models are mutable by default; safe to set
            tc.test_case_id = f"TC-{idx:03d}"  # type: ignore[attr-defined]
            changed = True

    # If your team prefers immutability, we can refactor to rebuild models instead.
