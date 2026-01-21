# src/test_data_design/test_data_schema.py
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field, AliasChoices


DATA_CONTRACT_VERSION = "TD-v1.0"


# -----------------------------
# Core components
# -----------------------------

class DataEntity(BaseModel):
    """
    Logical data entity used across datasets.
    """
    model_config = ConfigDict(extra="forbid")

    entity_name: str
    description: str
    key_fields: List[str] = Field(default_factory=list)

    # records are intentionally flexible but must remain JSON-serializable
    records: List[Dict[str, Any]] = Field(default_factory=list)


class DataSlice(BaseModel):
    """
    Subset of data with selectors defining how to pick records / interpret the slice.
    IMPORTANT: selectors MUST be a free-form dict and may contain arbitrary keys.
    """
    model_config = ConfigDict(extra="forbid")

    slice_id: str
    description: str

    # FREE-FORM dict. This is the key fix for your error.
    selectors: Dict[str, Any] = Field(default_factory=dict)

    expected_behavior_notes: List[str] = Field(default_factory=list)


class Dataset(BaseModel):
    """
    Dataset designed to support one or more test cases.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    dataset_id: str
    purpose: str

    linked_acceptance_criteria: List[str] = Field(default_factory=list)

    # Accept both variants from LLM output (robustness)
    linked_test_cases: List[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("linked_test_cases", "linked_test_case"),
    )

    entity_refs: List[str] = Field(default_factory=list)

    # flexible structure (we don't want schema churn here)
    data_profile: Dict[str, Any] = Field(default_factory=dict)

    data_slices: List[DataSlice] = Field(default_factory=list)


class NegativeOrEdgeData(BaseModel):
    """
    Invalid or edge-condition data for negative testing.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    case_id: str

    linked_acceptance_criteria: List[str] = Field(default_factory=list)

    linked_test_cases: List[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("linked_test_cases", "linked_test_case"),
    )

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

    generation_intent: Dict[str, Any] = Field(default_factory=dict)

    entities: List[DataEntity] = Field(default_factory=list)
    datasets: List[Dataset] = Field(default_factory=list)
    negative_and_edge_data: List[NegativeOrEdgeData] = Field(default_factory=list)

    assumptions_and_limits: List[str] = Field(default_factory=list)
