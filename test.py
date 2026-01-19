```python
# src/contracts/cir_schema.py
"""
Canonical Intermediate Representation (CIR) - CONTRACT-v1.0

This module defines the typed internal "language" for your agentic pipeline.
These schemas are STATIC (shared across all stories) and must be versioned.
Per-story runs will produce *instances* of these models.

Pydantic v2 models.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


CONTRACT_VERSION = "CONTRACT-v1.0"


# -------------------------
# Enums (keep tight + generic)
# -------------------------

class Priority(str, Enum):
    low = "Low"
    medium = "Medium"
    high = "High"
    critical = "Critical"
    unknown = "UNKNOWN"


class RiskLevel(str, Enum):
    low = "Low"
    medium = "Medium"
    high = "High"
    unknown = "UNKNOWN"


class RequirementType(str, Enum):
    functional = "functional"
    non_functional = "non_functional"


# -------------------------
# Core Models
# -------------------------

class StoryMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Prefer stable IDs from source systems; if not present, use filename stem
    story_id: str = Field(..., description="Stable story identifier (source ID or derived from filename).")
    name: str = Field(..., description="Story name/title.")
    state: str = Field(default="UNKNOWN", description="Lifecycle state (e.g., Defined/In Progress/Done).")
    owners: List[str] = Field(default_factory=list, description="Owners/roles responsible.")
    tags: List[str] = Field(default_factory=list, description="Tags/labels for grouping.")
    priority: Priority = Field(default=Priority.unknown)
    story_points: Optional[int] = Field(default=None, ge=0)
    iteration: str = Field(default="UNKNOWN", description="Planned iteration/sprint/PI.")
    release: str = Field(default="UNKNOWN", description="Release/train identifier.")


class Objective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(default="UNKNOWN", description="Actor/persona.")
    goal: str = Field(default="UNKNOWN", description="What they want to achieve.")
    benefit: str = Field(default="UNKNOWN", description="Why it matters / expected value.")


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    in_scope: List[str] = Field(default_factory=list)
    out_of_scope: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)


class AcceptanceCriterionCIR(BaseModel):
    """
    Canonical form of an acceptance criterion, normalized for downstream steps.
    Keep this generic: no domain entities required, just structured intent.
    """
    model_config = ConfigDict(extra="forbid")

    ac_id: str = Field(..., description="Acceptance criteria ID (e.g., AC 1).")
    description: str = Field(..., description="Sanitized description (no long prose).")

    preconditions: List[str] = Field(default_factory=list, description="Given/preconditions.")
    triggers: List[str] = Field(default_factory=list, description="When/triggers or user actions.")
    expected_outcome: List[str] = Field(default_factory=list, description="Then/expected outcomes.")

    notes: List[str] = Field(default_factory=list, description="Additional clarifications or TBD notes.")
    traceability_tags: List[str] = Field(default_factory=list, description="Tags for mapping tests back to ACs.")


class NFR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(..., description="Category (performance, security, UX, accessibility, etc.).")
    requirement: str = Field(..., description="Requirement text (kept short).")
    measurement_or_threshold_if_any: str = Field(default="TBD", description="Metric/threshold if specified.")
    testability_notes: List[str] = Field(default_factory=list, description="How to test/verify at high level.")


class UrlStateRequirements(BaseModel):
    """
    Generic way to represent any externalized state persistence requirements (URL, headers, storage, etc.).
    """
    model_config = ConfigDict(extra="forbid")

    externalized_state_required: bool = Field(default=False, description="Whether state must be persisted externally.")
    mechanism: str = Field(default="TBD", description="e.g., URL parameters, cookies, storage, etc.")
    rules: List[str] = Field(default_factory=list, description="Rules/constraints for the mechanism (TBD allowed).")


class DataEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Entity name (generic).")
    attributes: List[str] = Field(default_factory=list, description="Key attributes referenced by requirements.")
    constraints: List[str] = Field(default_factory=list, description="Constraints/validations (TBD allowed).")
    source: str = Field(default="UNKNOWN", description="Where the data originates (system/service/etc.).")


class DataEntitiesSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: List[DataEntity] = Field(default_factory=list)
    unknowns: List[str] = Field(default_factory=list, description="Data-related unknowns requiring clarification.")


class RiskItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk: str = Field(..., description="Risk statement (generic).")
    mitigation_test_idea: str = Field(default="TBD", description="High-level test idea to mitigate/cover the risk.")


class GlossaryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str
    meaning_or_TBD: str = Field(default="TBD")


class CanonicalUserStoryCIR(BaseModel):
    """
    Top-level canonical story representation used across the pipeline.
    This should be stable across all stories (instances vary; schema does not).
    """
    model_config = ConfigDict(extra="forbid")

    contract_version: str = Field(default=CONTRACT_VERSION)

    run_id: str = Field(..., description="Per-execution run identifier.")
    story_metadata: StoryMetadata
    objective: Objective
    scope: Scope

    functional_requirements: List[AcceptanceCriterionCIR] = Field(default_factory=list)

    nfrs: List[NFR] = Field(default_factory=list)

    state_and_external_persistence: UrlStateRequirements = Field(
        default_factory=UrlStateRequirements,
        description="External state persistence requirements (URL/storage/etc.)",
    )

    data_entities: DataEntitiesSection = Field(default_factory=DataEntitiesSection)

    risks: List[RiskItem] = Field(default_factory=list)

    glossary: List[GlossaryItem] = Field(default_factory=list)

    # Optional extension point (kept controlled)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional structured metadata (avoid prose).")
```
