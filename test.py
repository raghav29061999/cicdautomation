class NegativeOrEdgeData(BaseModel):
    """
    Invalid or edge-condition data sets.
    """
    model_config = ConfigDict(extra="forbid")

    case_id: str
    linked_acceptance_criteria: List[str]
    linked_test_cases: List[str]

    description: str
    invalid_records: List[Dict[str, Any]] = Field(default_factory=list)
    expected_validation_or_handling: List[str] = Field(default_factory=list)


class TestDataSuite(BaseModel):
    """
    Top-level TestData.json container.
    """
    model_config = ConfigDict(extra="forbid")

    run_id: str
    data_version: str = Field(default=DATA_CONTRACT_VERSION)

    generation_intent: Dict[str, Any]

    entities: List[DataEntity] = Field(default_factory=list)
    datasets: List[Dataset] = Field(default_factory=list)
    negative_and_edge_data: List[NegativeOrEdgeData] = Field(default_factory=list)

    assumptions_and_limits: List[str] = Field(default_factory=list)
2️⃣ generator.py
LLM-driven generation (similar to test_design.designer)

python
Copy code
# src/test_data_design/generator.py
from __future__ import annotations

import json
from typing import Any, Dict

from .test_data_schema import TestDataSuite


class TestDataGenerationError(Exception):
    """Raised when test data generation fails."""


class TestDataGenerator:
    """
    Generates TestData.json using LLM output.
    """

    def __init__(self, llm):
        self.llm = llm

    def generate(
        self,
        prompt_text: str,
        cir: Dict[str, Any],
        coverage: Dict[str, Any],
        test_cases: Dict[str, Any],
        ambiguity: Dict[str, Any] | None = None,
    ) -> TestDataSuite:
        """
        Calls LLM and parses TestData.json.
        """

        rendered_prompt = prompt_text.replace(
            "<PASTE CONTENT>",
            json.dumps(
                {
                    "CanonicalUserStoryCIR.json": cir,
                    "CoverageIntent.json": coverage,
                    "TestCases.json": test_cases,
                    "AmbiguityReport.json": ambiguity,
                },
                indent=2,
            ),
        )

        raw = self.llm.invoke(rendered_prompt)

        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            raise TestDataGenerationError(f"Invalid JSON from LLM: {e}") from e

        try:
            return TestDataSuite(**obj)
        except Exception as e:
            raise TestDataGenerationError(f"TestData schema validation failed: {e}") from e
3️⃣ validator.py
Governance rules (traceability, completeness)

python
Copy code
# src/test_data_design/validator.py
from __future__ import annotations

from typing import List, Set

from .test_data_schema import TestDataSuite


class TestDataValidationIssue(Exception):
    pass


class TestDataValidator:
    """
    Enforces governance rules beyond schema validation.
    """

    def validate(
        self,
        suite: TestDataSuite,
        known_ac_ids: Set[str],
        known_tc_ids: Set[str],
    ) -> None:
        issues: List[str] = []

        for ds in suite.datasets:
            if not set(ds.linked_acceptance_criteria).intersection(known_ac_ids):
                issues.append(f"{ds.dataset_id} has no valid AC linkage")

            if not set(ds.linked_test_cases).intersection(known_tc_ids):
                issues.append(f"{ds.dataset_id} has no valid TC linkage")

        for neg in suite.negative_and_edge_data:
            if not set(neg.linked_acceptance_criteria).intersection(known_ac_ids):
                issues.append(f"{neg.case_id} has no valid AC linkage")

            if not set(neg.linked_test_cases).intersection(known_tc_ids):
                issues.append(f"{neg.case_id} has no valid TC linkage")

        if issues:
            raise TestDataValidationIssue(
                "TestData governance validation failed:\n" + "\n".join(issues)
            )
4️⃣ mappings.py
Reusable helpers (kept deliberately small)

python
Copy code
# src/test_data_design/mappings.py
"""
Helper utilities for mapping CIR entities to data fields.
Kept lightweight on purpose.
"""

from typing import List, Dict, Any


def minimal_generic_fields() -> List[str]:
    """
    Fallback fields when CIR data_entities lack attributes.
    """
    return ["id", "type", "status"]


def ensure_records_have_keys(
    records: List[Dict[str, Any]], keys: List[str]
) -> List[Dict[str, Any]]:
    """
    Ensures every record has all key fields.
    """
    out = []
    for idx, r in enumerate(records, start=1):
        r2 = dict(r)
        for k in keys:
            r2.setdefault(k, f"{k}-{idx:03d}")
        out.append(r2)
    return out
5️⃣ __init__.py
python
Copy code
# src/test_data_design/__init__.py
"""
Synthetic Test Data Design (T2).

Responsible for:
- Generating TestData.json
- Validating traceability to ACs and TCs
- Keeping data generic, deterministic, and safe
"""

