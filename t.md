# Framework Evaluation Matrix (Story-Agnostic)

## Evidence Basis (Sanitized)
- Evidence reviewed: Phase-1 artifacts (CIR, ambiguity logs, coverage intent, run manifest, contract deltas)
- Note: Requirements below are intentionally generalized to avoid revealing story content.

## Derived System Requirements (Generalized)

### Control Flow
- Explicit step-gated, multi-step pipeline with clear stage boundaries (e.g., derive expected state, execute action, validate outcomes).
- Support for conditional branching based on runtime signals (e.g., different paths for “valid input” vs “malformed/unknown input” vs “empty outcomes”).
- Ability to model repeated user-driven transitions (e.g., apply → apply again quickly → clear → reapply) without state corruption.
- Concurrency/race-awareness: ability to represent “in-flight update” and prevent/queue conflicting steps.
- Support for multi-dimensional combination logic validation (within-group combination vs across-group combination) in a repeatable way.

### State & Memory
- Strong per-run state object with isolation between runs (no cross-run leakage).
- State persistence across steps, including externalized state persistence mechanism (generalized from “deep-link/shareable state” requirements).
- Deterministic canonicalization of externally persisted state (stable ordering/encoding/normalization) once rules are defined.
- Ability to carry both “expected” and “observed” state (UI/API/URL equivalents generalized to “external interface state” and “system response state”) for oracle evaluation.
- Support for unknown/TBD fields as first-class placeholders while still producing valid artifacts.

### Validation & Failure Handling
- Schema-gated checkpoints at multiple stages (inputs, intermediate derived expectations, final outputs).
- Ability to halt/hold execution on high ambiguity and emit structured “needs-clarification” outputs (without inventing defaults).
- Typed failure propagation with specific failure categories (e.g., externalized-state mismatch, combination-logic mismatch, count consistency mismatch, interaction-blocking failure).
- Deterministic test oracles must be representable even when some requirements remain TBD, via explicit “UNKNOWN/TBD” handling.

### Observability & Replay
- Step-level logging with stable identifiers (run_id, step_id) and artifact pinning for every stage.
- Replayability: rehydrate a run using stored inputs + pinned contracts + deterministic settings to reproduce the same sequence and outputs.
- Ability to attach evidence bundles (e.g., captured external interface snapshots, request/response traces generalized) per step.
- Support for defining and consuming stable completion signals for asynchronous updates (generalized “loading start/end” and “results updated” signals).

### Governance & Determinism
- Contract version pinning across schemas/specs/taxonomies and enforcement of “no runtime drift.”
- Deterministic execution mode configuration (temperature/seed discipline, stable ordering, no hidden retries that change outputs).
- Clear separation between: (a) static contracts (schemas/taxonomies), (b) per-run manifests, and (c) per-run produced artifacts.
- Ability to evolve the system with additive contract deltas (new enums/fields) without breaking existing runs.

## Evaluation Matrix

| Capability / Requirement | LangChain | LangGraph | Strands | Custom Python |
|--------------------------|-----------|-----------|---------|---------------|
| Explicit step boundaries / gating | ⚠️ | ✅ | ⚠️ | ✅ |
| Conditional branching & stop conditions | ⚠️ | ✅ | ⚠️ | ✅ |
| Concurrency/race-aware modeling (in-flight/queue) | ❌ | ⚠️ | ❌ | ⚠️ |
| Typed per-run state passing | ⚠️ | ⚠️ | ⚠️ | ✅ |
| State persistence across steps (rehydration-friendly) | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Externalized state canonicalization (deterministic) | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Schema validation checkpoints (multiple gates) | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Stop/hold on high ambiguity (structured) | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Typed failure propagation with taxonomy alignment | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Deterministic execution controls (no hidden drift) | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Observability hooks (step logs, artifacts) | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Replayability (run rehydration + repeatable order) | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Contract version pinning & enforcement | ❌ | ❌ | ❌ | ✅ |

Legend: ✅ Supported natively | ⚠️ Supported with workarounds / risk | ❌ Not supported / conflicts with requirement

## Framework-Specific Analysis (Sanitized)

### LangChain
- Fit assessment:
  - Good for composing tool-calls and linear chains, but tends to blur “explicit step contract boundaries” unless you impose strict wrappers.
  - Control flow beyond linear sequences often becomes implicit (callbacks, agent loops), which is risky for deterministic, contract-driven pipelines.
- Workarounds required:
  - Build a strict “run controller” around chains to enforce: step IDs, schema gates, pinned settings, and stable ordering.
  - Implement your own replay store and artifact persistence; treat LangChain as an execution library, not the orchestrator.
  - Avoid agentic auto-loops or constrain them heavily (fixed max-steps, explicit stop rules) to reduce drift.
- Primary risks (architecture/ops/maintainability):
  - Architectural: abstraction leaks via hidden retries/tool selection, implicit branching, and framework-driven control flow.
  - Operational: harder to guarantee replayability and determinism without deep instrumentation; debugging often requires framework internals familiarity.
  - Maintainability: ecosystem churn and version drift can change defaults; upgrades risk altering execution behavior.

### LangGraph
- Fit assessment:
  - Stronger match for explicit graph-based control flow (branching, loops) and “step as a node” modeling, which aligns with gated pipelines.
  - Still requires careful discipline for determinism and contract pinning; state typing is possible but not inherently contract-enforced.
- Workarounds required:
  - Define a strict state schema and enforce validation at node boundaries (pre/post conditions) externally or via wrappers.
  - Implement contract version enforcement and run rehydration persistence as a first-class layer.
  - Model concurrency/race conditions explicitly (e.g., in-flight flags, event ordering) and keep execution single-threaded where determinism is mandatory.
- Primary risks (architecture/ops/maintainability):
  - Architectural: graph complexity can grow quickly; if not governed, it becomes a “logic maze” with hard-to-audit transitions.
  - Operational: replay is feasible but only if all inputs/events and ordering are captured; async steps can introduce nondeterministic interleavings.
  - Maintainability: coupling to graph conventions; refactors can be disruptive without strong migration tooling and compatibility discipline.

### Strands
- Fit assessment:
  - Potentially helpful for higher-level agent patterns, but typically optimized for flexible agent behavior rather than strict contract-gated determinism.
  - If it encourages implicit decision-making or dynamic tool routing, it conflicts with “no runtime drift” governance goals.
- Workarounds required:
  - Constrain the runtime: fixed step plans, explicit transitions, explicit stopping criteria, disabled/limited autonomy.
  - Wrap with a deterministic run engine: schema gates, artifact pinning, stable ordering, and explicit failure taxonomy mapping.
- Primary risks (architecture/ops/maintainability):
  - Architectural: hidden control flow and “agent autonomy” are hard to reconcile with strict determinism and auditability.
  - Operational: instrumentation/replay often becomes “best effort” unless the framework exposes deep hooks.
  - Maintainability: risk of lock-in to framework-specific abstractions and rapidly evolving APIs.

### Custom Python Orchestration (no agent framework)
- Fit assessment:
  - Best alignment with strict determinism, schema gates, contract version pinning, and replayability requirements.
  - Enables designing the pipeline directly around run manifests, explicit step functions, and validation checkpoints.
- Workarounds required:
  - You must build or standardize: graph/branch modeling (if needed), artifact persistence, observability conventions, and developer ergonomics.
  - If complex branching/loops become common, you may need a lightweight internal DAG/state-machine library (still within your governance model).
- Primary risks (architecture/ops/maintainability):
  - Architectural: risk of reinventing orchestration patterns poorly (ad-hoc branching, inconsistent step interfaces) without strong standards.
  - Operational: initial investment is higher; reliability depends on disciplined engineering (logging, storage, idempotency).
  - Maintainability: long-term success depends on documentation, templates, and strong review practices; otherwise divergence across teams is likely.

## Key Trade-offs (Sanitized)
- Determinism & governance vs speed of adoption: higher-level agent frameworks accelerate prototyping but introduce hidden behavior that undermines strict replay and contract pinning.
- Explicitness vs convenience: graph/state-machine approaches better express branching and stop/hold logic, but require governance to prevent complexity sprawl.
- Observability/replay ownership: regardless of framework, enterprise-grade replayability typically requires a dedicated run-store + artifact model; relying on framework defaults is risky.
- Handling TBD/UNKNOWN requirements: systems that treat “unknowns” as first-class and can hard-stop with structured ambiguity outputs align better with strict pipelines.

## Frameworks That Fail Critical Requirements
- LangChain: ❌ Contract version pinning & enforcement (must be external), ❌ concurrency/race modeling (not a native focus); determinism/replay rely on substantial wrapping.
- LangGraph: ❌ Contract version pinning & enforcement (must be external); concurrency/race modeling is ⚠️ and requires disciplined modeling.
- Strands: ❌ Contract version pinning & enforcement (must be external), ❌ concurrency/race modeling (not a native focus); autonomy-oriented behavior risks determinism drift.

## Frameworks That Align with Requirements
- Custom Python Orchestration: strongest alignment for determinism, schema gates, replayability, and contract governance (with the trade-off of higher build effort).
- LangGraph: good alignment for explicit branching/step modeling, but requires an external governance layer for contract pinning, schema gates, and deterministic replay discipline.
