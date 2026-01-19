# src/contracts/versions.py
"""
Contract Version Registry

This module defines version identifiers for all STATIC system contracts.
These versions are referenced by every pipeline run (via RunManifest)
to guarantee determinism, replayability, and auditability.

IMPORTANT RULE:
- Versions change ONLY through deliberate code changes and review.
- Versions MUST NOT be modified at runtime or by LLMs.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ContractVersions:
    """
    Central registry of contract versions.

    Each version represents a stable, reviewed contract.
    Any change to the corresponding contract requires a version bump.
    """
    CIR_SCHEMA: str = "CONTRACT-v1.0"
    VALIDATION_SPEC: str = "CONTRACT-v1.0"
    FAILURE_TAXONOMY: str = "CONTRACT-v1.0"
    OBSERVABILITY_SPEC: str = "CONTRACT-v1.0"
    CONTROL_FLOW: str = "CONTRACT-v1.0"
    MEMORY_SEMANTICS: str = "CONTRACT-v1.0"


# Singleton-style access (intentional)
VERSIONS = ContractVersions()

