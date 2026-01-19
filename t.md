# src/contracts/validation_spec.py
"""
Validation Specification (CONTRACT-v1.0)

This module defines GOVERNANCE rules that are STATIC and shared across all user stories.
It is intentionally separate from CIR schema/models:
- cir_schema.py defines the structure ("language")
- validation_spec.py defines what is considered valid, complete, and acceptable ("policy")

Key principles:
- Deterministic validation (no probabilistic checks)
- Typed, actionable errors
- No domain coupling (generic engineering rules)
- Versioned contracts (do not modify at runtime)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple

from pydantic import BaseModel, Field, ConfigDict

from .cir_schema import CanonicalUserStoryCIR
from .versions import VERSIONS


# -------------------------
# Validation error model
# -------------------------

class ValidationErrorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., description="Stable error code.")
    severity: str = Field(..., description="low|medium|high")
    location: str = Field(..., description="Pointer-like location path (e.g., story_metadata.name).")
    message: str = Field(..., description="Human-readable message.")
    suggested_fix: str = Field(default="TBD", description="Concrete remediation guidance.")
    notes: Optional[str] = Field(default=None)


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = Field(default=VERSIONS.VALIDATION_SPEC)
    is_valid: bool
    errors: List[ValidationErrorItem] = Field(default_factory=list)
    warnings: List[ValidationErrorItem] = Field(default_factory=list)

    def add_error(self, item: ValidationErrorItem) -> None:
        self.errors.append(item)

    def add_warning(self, item: ValidationErrorItem) -> None:
        self.warnings.append(item)


# -------------------------
# Policy configuration
# -------------------------

@dataclass(frozen=True)
class ValidationPolicy:
    """
    Static governance rules for validating CIR instances.
    Keep these rules generic and deterministic.
    """
    # Minimum required counts
    min_acceptance_criteria: int = 1
    min_preconditions_per_ac: int = 0
    min_expected_outcomes_per_ac: int = 1

    # Limits to prevent runaway verbosity / non-deterministic inflation
    max_acceptance_criteria: int = 50
    max_steps_like_items_per_ac: int = 50  # preconditions+triggers+expected_outcome total cap

    # TBD / UNKNOWN policy
    allow_tbd_fields: bool = True
    max_tbd_density_ratio: float = 0.35  # if too many TBDs, mark as warning/high risk

    # Generic requirement: if externalized state required, rules should be present
    require_rules_if_externalized_state: bool = True

    # Basic metadata requirements
    require_story_name: bool = True
    require_story_id: bool = True


DEFAULT_POLICY = ValidationPolicy()


# -------------------------
# Helper functions
# -------------------------

def _count_tbd_unknown(values: List[str]) -> Tuple[int, int]:
    """
    Returns (tbd_unknown_count, total_count) for a list of strings.
    """
    total = len(values)
    tbd = 0
    for v in values:
        s = (v or "").strip().upper()
        if s in {"TBD", "UNKNOWN"} or s.startswith("TBD") or s.startswith("UNKNOWN"):
            tbd += 1
    return tbd, total


def _safe_path(*parts: str) -> str:
    return ".".join(parts)


# -------------------------
# Main validator
# -------------------------

def validate_cir(cir: CanonicalUserStoryCIR, policy: ValidationPolicy = DEFAULT_POLICY) -> ValidationReport:
    """
    Validate a CanonicalUserStoryCIR instance against governance rules.

    Returns a ValidationReport with:
    - errors: violations that should fail the pipeline step (hard stop)
    - warnings: violations that should be surfaced but may allow proceed (soft stop)

    Note: This function does NOT mutate the CIR.
    """
    report = ValidationReport(is_valid=True)

    # ---- Metadata checks ----
    if policy.require_story_id and not (cir.story_metadata.story_id or "").strip():
        report.add_error(
            ValidationErrorItem(
                code="VAL-META-001",
                severity="high",
                location=_safe_path("story_metadata", "story_id"),
                message="Missing required story_id.",
                suggested_fix="Populate story_id from source system or filename stem."
            )
        )

    if policy.require_story_name and not (cir.story_metadata.name or "").strip():
        report.add_error(
            ValidationErrorItem(
                code="VAL-META-002",
                severity="high",
                location=_safe_path("story_metadata", "name"),
                message="Missing required story name/title.",
                suggested_fix="Populate story name from story header/title."
            )
        )

    # ---- Acceptance criteria checks ----
    ac_count = len(cir.functional_requirements)
    if ac_count < policy.min_acceptance_criteria:
        report.add_error(
            ValidationErrorItem(
                code="VAL-AC-001",
                severity="high",
                location=_safe_path("functional_requirements"),
                message=f"At least {policy.min_acceptance_criteria} acceptance criterion is required; found {ac_count}.",
                suggested_fix="Extract acceptance criteria from story text or mark story as ambiguous and stop."
            )
        )

    if ac_count > policy.max_acceptance_criteria:
        report.add_warning(
            ValidationErrorItem(
                code="VAL-AC-002",
                severity="medium",
                location=_safe_path("functional_requirements"),
                message=f"High number of acceptance criteria ({ac_count}) may indicate over-segmentation.",
                suggested_fix="Confirm whether ACs should be grouped or whether scope is too broad."
            )
        )

    # ---- Per-AC content checks ----
    total_strings: List[str] = []
    tbd_strings: List[str] = []

    for i, ac in enumerate(cir.functional_requirements):
        ac_path = f"functional_requirements[{i}]"

        if not (ac.ac_id or "").strip():
            report.add_error(
                ValidationErrorItem(
                    code="VAL-AC-003",
                    severity="high",
                    location=_safe_path(ac_path, "ac_id"),
                    message="Acceptance criterion is missing ac_id.",
                    suggested_fix="Assign stable ac_id (e.g., AC-1, AC-2) preserving original order."
                )
            )

        if not (ac.description or "").strip():
            report.add_error(
                ValidationErrorItem(
                    code="VAL-AC-004",
                    severity="high",
                    location=_safe_path(ac_path, "description"),
                    message="Acceptance criterion is missing description.",
                    suggested_fix="Add a short, generic description derived from the story text."
                )
            )

        # Expect at least one expected outcome (Then)
        if len(ac.expected_outcome) < policy.min_expected_outcomes_per_ac:
            report.add_error(
                ValidationErrorItem(
                    code="VAL-AC-005",
                    severity="high",
                    location=_safe_path(ac_path, "expected_outcome"),
                    message="Acceptance criterion must include at least one expected outcome.",
                    suggested_fix="Extract 'Then' behavior from story; if missing, log ambiguity and stop."
                )
            )

        # Cap total step-like items to avoid inflation
        step_like_total = len(ac.preconditions) + len(ac.triggers) + len(ac.expected_outcome)
        if step_like_total > policy.max_steps_like_items_per_ac:
            report.add_warning(
                ValidationErrorItem(
                    code="VAL-AC-006",
                    severity="medium",
                    location=_safe_path(ac_path),
                    message=f"Acceptance criterion has many step-like items ({step_like_total}); may be too verbose.",
                    suggested_fix="Consolidate steps while preserving meaning; avoid splitting into micro-steps."
                )
            )

        # Track TBD density
        total_strings.extend(ac.preconditions + ac.triggers + ac.expected_outcome + [ac.description])
        for s in ac.preconditions + ac.triggers + ac.expected_outcome + [ac.description]:
            if (s or "").strip().upper().startswith(("TBD", "UNKNOWN")) or (s or "").strip().upper() in {"TBD", "UNKNOWN"}:
                tbd_strings.append(s)

    # ---- Externalized state rules ----
    if cir.state_and_external_persistence.externalized_state_required and policy.require_rules_if_externalized_state:
        if not cir.state_and_external_persistence.rules:
            report.add_warning(
                ValidationErrorItem(
                    code="VAL-STATE-001",
                    severity="medium",
                    location=_safe_path("state_and_external_persistence", "rules"),
                    message="Externalized state persistence is required but no rules were captured.",
                    suggested_fix="Add at least one rule describing persistence format/constraints; otherwise mark TBD and raise ambiguity."
                )
            )

    # ---- TBD density checks (warning-level by default) ----
    tbd_count, total_count = _count_tbd_unknown(total_strings)
    if total_count > 0:
        ratio = tbd_count / total_count
        if not policy.allow_tbd_fields and tbd_count > 0:
            report.add_error(
                ValidationErrorItem(
                    code="VAL-TBD-001",
                    severity="high",
                    location="*",
                    message="TBD/UNKNOWN values are not allowed by current policy.",
                    suggested_fix="Resolve all TBD/UNKNOWN items before proceeding."
                )
            )
        elif ratio > policy.max_tbd_density_ratio:
            report.add_warning(
                ValidationErrorItem(
                    code="VAL-TBD-002",
                    severity="medium",
                    location="*",
                    message=f"High TBD/UNKNOWN density detected ({ratio:.0%}). This may reduce downstream determinism.",
                    suggested_fix="Review ambiguities and resolve high-impact TBDs before generating scripts/data."
                )
            )

    # ---- Finalize validity ----
    if report.errors:
        report.is_valid = False

    return report
