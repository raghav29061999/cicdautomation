# Fix Suggestion — Preserve Original User Intent Through Refinement
## Problem Summary
The current issue is no longer mainly about invalid combinations of measure, population, and grouping.
That earlier validation fix is useful because it prevents incompatible query combinations.
The new problem is different:
> The refinement flow is losing important constraints from the original user question.
For the question:
> Count claims for Elzonris and Krystexxa by the selected program and time period.
the final response should preserve all of the following:
- Metric: claim count
- Drug filters:
  - Elzonris
  - Krystexxa
- Selected program
- Selected time period
- Comparison intent between the two drugs
Instead, the refined request appears to become something more generic such as:
> Show claim counts grouped by drug.
Once the named drugs and time period are lost, the downstream system can produce a technically valid response, such as the top 10 drugs, while still answering the wrong question.
---
## Root Cause
The refinement output appears to be treated as a replacement for the original user intent.
Conceptually, the current behaviour may be similar to:
```python
state["intent"] = refinement_output

This is dangerous because the refinement step usually contains only the fields being refined.

For example:

{
  "group_by": "drug"
}

If this replaces the original intent, the system loses:

{
  "drug_names": ["Elzonris", "Krystexxa"],
  "program": "...",
  "time_period": "..."
}

The refinement process should therefore modify the original intent rather than recreate it.

⸻

Recommended Design

Create a structured representation of the original request and preserve it throughout the complete request lifecycle.

Example:

{
  "metric": "claim_count",
  "entities": {
    "drug_names": [
      "Elzonris",
      "Krystexxa"
    ]
  },
  "filters": {
    "program": "<selected_program>",
    "time_period": "<selected_time_period>"
  },
  "group_by": "drug",
  "comparison": true
}

Store this as the original intent.

Then refinement should create only a delta.

Example refinement:

{
  "group_by": "drug"
}

The final effective intent should be created using:

EFFECTIVE_INTENT = ORIGINAL_INTENT + REFINEMENT_DELTA

and not:

EFFECTIVE_INTENT = REFINEMENT_OUTPUT

⸻

Expected Merge Behaviour

Original intent:

{
  "metric": "claim_count",
  "drug_names": [
    "Elzonris",
    "Krystexxa"
  ],
  "program": "Commercial",
  "time_period": "Q2 2026"
}

Refinement:

{
  "group_by": "drug"
}

Correct result:

{
  "metric": "claim_count",
  "drug_names": [
    "Elzonris",
    "Krystexxa"
  ],
  "program": "Commercial",
  "time_period": "Q2 2026",
  "group_by": "drug"
}

Incorrect result:

{
  "metric": "claim_count",
  "group_by": "drug"
}

The second version silently broadens the user’s request and makes a Top-N response possible.

⸻

Make Original User Constraints “Sticky”

Explicit constraints from the original user question should remain active unless the user explicitly changes or removes them.

Examples of sticky constraints:

Elzonris
Krystexxa
Commercial program
Q2 2026
claim_count

Recommended precedence:

Latest explicit user change
        >
Original explicit user constraint
        >
Refinement inference
        >
System/default inference

This prevents an inferred refinement field from replacing something the user explicitly asked for.

⸻

Add Constraint Provenance

Each field should contain information about where it came from.

Example:

{
  "drug_names": {
    "value": [
      "Elzonris",
      "Krystexxa"
    ],
    "source": "original_user_query",
    "explicit": true
  },
  "group_by": {
    "value": "drug",
    "source": "refinement",
    "explicit": true
  }
}

This helps both validation and debugging.

The system can then apply a simple rule:

A lower-priority inferred value cannot remove a higher-priority
explicit user constraint.

⸻

Separate Filters From Grouping

This is especially important for the current issue.

In:

Count claims for Elzonris and Krystexxa.

the drug names are filters.

{
  "drug_filter": [
    "Elzonris",
    "Krystexxa"
  ]
}

Whereas:

{
  "group_by": "drug"
}

only describes how results should be organized.

The system must never interpret:

group_by = drug

as meaning:

query all drugs

The expected logical SQL should look similar to:

SELECT
    drug_name,
    COUNT(*) AS claim_count
FROM claims
WHERE
    drug_name IN ('Elzonris', 'Krystexxa')
    AND program = :program
    AND service_date BETWEEN :start_date AND :end_date
GROUP BY drug_name;

It should not become:

SELECT
    drug_name,
    COUNT(*) AS claim_count
FROM claims
GROUP BY drug_name
ORDER BY claim_count DESC
LIMIT 10;

unless the user explicitly asks for:

top drugs
highest claim count drugs
rank drugs
top 10 drugs

⸻

Prevent Automatic Top-N Behaviour

There may currently be logic similar to:

if group_by == "drug":
    return top_drugs()

That behaviour should be removed.

Instead, determine query mode from the actual intent.

Example:

if explicit_entities:
    query_mode = "FILTERED_ENTITY_QUERY"
elif ranking_requested:
    query_mode = "TOP_N_QUERY"
else:
    query_mode = "AGGREGATION_QUERY"

Therefore:

Elzonris + Krystexxa

should automatically force:

FILTERED_ENTITY_QUERY

unless the user explicitly requests otherwise.

⸻

Add an Intent Preservation Validator

Before query generation or tool execution, compare the final effective intent with the original user intent.

Example:

def validate_intent_preservation(
    original_intent,
    effective_intent
):
    original_drugs = set(
        original_intent.get("drug_names", [])
    )
    final_drugs = set(
        effective_intent.get("drug_names", [])
    )
    if original_drugs and not final_drugs:
        raise IntentPreservationError(
            "Drug filters were lost during refinement."
        )
    if original_drugs != final_drugs:
        raise IntentPreservationError(
            "Requested drug entities changed during refinement."
        )
    if (
        original_intent.get("program")
        and not effective_intent.get("program")
    ):
        raise IntentPreservationError(
            "Program constraint was lost during refinement."
        )
    if (
        original_intent.get("time_period")
        and not effective_intent.get("time_period")
    ):
        raise IntentPreservationError(
            "Time-period constraint was lost during refinement."
        )

This check should happen before SQL generation.

⸻

Add a Query Plan Validation Layer

After the effective intent is created, generate a structured query plan before producing SQL.

Example:

{
  "query_type": "filtered_aggregation",
  "metric": "claim_count",
  "filters": {
    "drug_name": [
      "Elzonris",
      "Krystexxa"
    ],
    "program": "Commercial",
    "time_period": "Q2 2026"
  },
  "group_by": [
    "drug_name"
  ],
  "ranking": null,
  "limit": null
}

Then validate the query plan against the effective intent.

For example:

if effective_intent["drug_names"]:
    assert query_plan["filters"]["drug_name"]
if not effective_intent.get("ranking_requested"):
    assert query_plan["ranking"] is None
    assert query_plan["limit"] is None

This catches the error before SQL execution.

⸻

Add an Answer Contract

Before generating the final natural-language response, create a small contract describing what the answer is required to contain.

For this case:

{
  "required_entities": [
    "Elzonris",
    "Krystexxa"
  ],
  "required_metric": "claim_count",
  "required_context": [
    "program",
    "time_period"
  ],
  "expected_result_shape": "two_entity_comparison",
  "ranking_allowed": false
}

This becomes the specification for the final response.

⸻

Validate Structured Results Before Validating Text

If possible, do not first validate the generated natural-language response.

Validate the execution result itself.

Expected result:

{
  "rows": [
    {
      "drug_name": "Elzonris",
      "claim_count": 123
    },
    {
      "drug_name": "Krystexxa",
      "claim_count": 456
    }
  ]
}

Then check:

expected = {
    "Elzonris",
    "Krystexxa"
}
actual = {
    row["drug_name"]
    for row in result["rows"]
}
if actual != expected:
    raise ResultValidationError(
        "Execution result does not match requested entities."
    )

This is much stronger than asking an LLM whether the final answer “looks correct.”

⸻

Add Final Question-Answer Alignment Validation

The current validation appears to catch things such as:

Is the answer empty?
Is the answer malformed?
Did the tool return an error?

That is necessary but insufficient.

A response can be:

valid
well formed
confident
grammatically correct

and still answer a completely different question.

Add a final validation such as:

def validate_answer_contract(
    contract,
    structured_result,
    final_answer
):
    for entity in contract["required_entities"]:
        if entity.lower() not in final_answer.lower():
            return False, (
                f"Missing requested entity: {entity}"
            )
    if contract["required_metric"] == "claim_count":
        if not structured_result.get("rows"):
            return False, "Claim counts missing."
    return True, None

Where possible, validate against structured result fields rather than relying only on string matching.

⸻

Missing Program or Time Period Should Trigger Clarification

If the request says:

selected program and time period

but either value cannot be resolved from UI/session state, the query should not proceed using a default value.

Instead:

{
  "status": "clarification_required",
  "missing_fields": [
    "time_period"
  ]
}

or:

{
  "status": "clarification_required",
  "missing_fields": [
    "program",
    "time_period"
  ]
}

The assistant should then ask the user for the missing information.

Do not silently use:

all time
current year
all programs
default program

unless that behaviour is explicitly part of the product specification.

⸻

Recommended State Design

Keep the original and derived versions separately.

Example:

class QueryState(TypedDict):
    original_question: str
    original_intent: dict
    refinement_delta: dict
    effective_intent: dict
    answer_contract: dict
    query_plan: dict
    generated_sql: str
    execution_result: dict
    final_answer: str
    validation_result: dict

Do not overwrite:

original_intent

during refinement.

⸻

Recommended Flow

User Question
      ↓
Extract Original Intent
      ↓
Store Original Intent
      ↓
Generate Refinement Options
      ↓
User Selects Refinement
      ↓
Create Refinement Delta
      ↓
Merge With Original Intent
      ↓
Effective Intent
      ↓
INTENT PRESERVATION VALIDATION
      ↓
Measure / Population / Grouping Compatibility Validation
      ↓
Create Answer Contract
      ↓
Generate Query Plan
      ↓
QUERY PLAN VS INTENT VALIDATION
      ↓
Generate SQL / Tool Request
      ↓
Execute Query
      ↓
RESULT SHAPE VALIDATION
      ↓
Generate Final Response
      ↓
ANSWER CONTRACT VALIDATION
      ↓
Return Response

⸻

Important Ordering

The compatibility validation you already added should remain.

However, the validations solve different problems.

Use:

1. Intent Preservation Validation
2. Measure/Population/Grouping Compatibility Validation
3. Query Plan Validation
4. Execution Result Validation
5. Final Answer Validation

The earlier fix answers:

"Is this combination technically valid?"

The new validation answers:

"Are we still answering the question the user actually asked?"

Both are required.

⸻

Suggested Merge Implementation

Instead of:

state["intent"] = refinement_output

implement something similar to:

def merge_intent(
    original_intent: dict,
    refinement: dict
) -> dict:
    merged = original_intent.copy()
    for key, value in refinement.items():
        if value is None:
            continue
        merged[key] = value
    return merged

However, for production usage, use field-level merge rules rather than a simple dictionary update.

For example:

PROTECTED_FIELDS = {
    "drug_names",
    "program",
    "time_period",
    "metric"
}

Then:

def merge_intent(original, refinement):
    merged = original.copy()
    for key, value in refinement.items():
        if value is None:
            continue
        if key in PROTECTED_FIELDS:
            if refinement.get(
                f"{key}_explicitly_changed",
                False
            ):
                merged[key] = value
        else:
            merged[key] = value
    return merged

This prevents inferred refinement output from accidentally removing explicit constraints.

⸻

Better Option — Use Immutable Constraints

An even safer structure would be:

{
  "constraints": {
    "immutable": {
      "drug_names": [
        "Elzonris",
        "Krystexxa"
      ],
      "program": "Commercial",
      "time_period": "Q2 2026"
    },
    "refinable": {
      "group_by": "drug",
      "aggregation": "count"
    }
  }
}

“Immutable” does not mean the user can never change it.

It means:

the system cannot change it implicitly

Only an explicit user instruction can modify it.

⸻

Add Trace Logging

Add structured logging for every stage.

Example:

Original Question
    ↓
Original Intent
    ↓
Refinement Delta
    ↓
Effective Intent
    ↓
Query Mode
    ↓
Query Plan
    ↓
Generated SQL
    ↓
Execution Result
    ↓
Final Answer

For this exact failing example, inspect each stage and find the first point where:

Elzonris
Krystexxa
program
time_period

disappear.

That stage is the actual source of the bug.

⸻

Example Debug Trace

Expected:

{
  "original_intent": {
    "metric": "claim_count",
    "drug_names": [
      "Elzonris",
      "Krystexxa"
    ],
    "program": "Commercial",
    "time_period": "Q2 2026"
  },
  "refinement_delta": {
    "group_by": "drug"
  },
  "effective_intent": {
    "metric": "claim_count",
    "drug_names": [
      "Elzonris",
      "Krystexxa"
    ],
    "program": "Commercial",
    "time_period": "Q2 2026",
    "group_by": "drug"
  },
  "query_mode": "FILTERED_ENTITY_QUERY"
}

If you instead see:

{
  "effective_intent": {
    "metric": "claim_count",
    "group_by": "drug"
  }
}

then the refinement merge is the primary bug.

If effective intent is correct but the query plan becomes:

{
  "ranking": "DESC",
  "limit": 10
}

then the bug exists in query planning.

If the query plan is correct but the SQL queries all drugs, the bug is in SQL generation.

If SQL/result is correct but the response discusses unrelated drugs, the bug is in answer generation.

This trace will therefore tell you exactly which layer needs to be fixed.

⸻

Test Cases To Add

Test 1 — Preserve Named Entities

Input:

Count claims for Elzonris and Krystexxa.

Refinement:

{
  "group_by": "drug"
}

Expected effective intent:

{
  "drug_names": [
    "Elzonris",
    "Krystexxa"
  ],
  "group_by": "drug"
}

The drug filter must not disappear.

⸻

Test 2 — Preserve Time Period

Input:

Count claims for Elzonris and Krystexxa
during Q2 2026.

After every refinement stage:

time_period = Q2 2026

must remain present.

⸻

Test 3 — Preserve Program

Input:

Count claims for Elzonris and Krystexxa
for Commercial.

The query plan must still contain:

program = Commercial

after refinement.

⸻

Test 4 — No Automatic Top-N

Input:

Count claims for Elzonris and Krystexxa.

Forbidden query behaviour:

ORDER BY claim_count DESC
LIMIT 10

unless the user explicitly asks for ranking.

⸻

Test 5 — Explicit Top-N Still Works

Input:

Show the top 10 drugs by claim count.

Expected:

TOP_N_QUERY

This confirms that fixing this issue does not break legitimate ranking requests.

⸻

Test 6 — Missing Time Period

Input:

Count claims for Elzonris and Krystexxa
for the selected time period.

If no selected time period exists:

Expected:

{
  "status": "clarification_required",
  "missing_fields": [
    "time_period"
  ]
}

Do not execute a broad query.

⸻

Test 7 — Answer Contract Failure

Requested:

Elzonris
Krystexxa

Generated answer contains:

Drug A
Drug B
Drug C
...

Expected:

ANSWER_VALIDATION_FAILED

The response should not be returned to the user.

⸻

Test 8 — One Drug Missing

Expected result:

Elzonris
Krystexxa

Execution returns only:

Elzonris

Expected:

RESULT_VALIDATION_FAILED

Do not generate a normal answer without identifying the missing entity.

⸻

Recommended Implementation Priority

P0 — Fix the Actual Data Loss

Implement first:

Preserve original intent in state
Use refinement as delta
Merge rather than replace
Preserve explicit drug filters
Preserve program
Preserve time period
Prevent implicit Top-N

This is the main fix for the current issue.

⸻

P1 — Add Intent Validation

Before query execution:

Compare original_intent
with
effective_intent

Fail if important explicit constraints disappear.

⸻

P2 — Add Structured Query Plan Validation

Validate that:

explicit drug entities
        ↓
drug filters

are present in the query plan.

Also validate that:

ranking_requested = false

means:

limit = null
ranking = null

⸻

P3 — Add Result and Answer Contracts

Validate:

requested entities
requested metric
program
time period
result shape

before returning the response.

⸻

P4 — Improve Observability

Trace:

original_question
original_intent
refinement_delta
effective_intent
query_plan
generated_sql
execution_result
final_answer
validation_result

This will make future mismatches much easier to diagnose.

⸻

What I Would Change First

If I were debugging this implementation, I would first locate the code where the refinement result is passed to the downstream agent/query generator.

Look specifically for behaviour equivalent to:

state["intent"] = refinement_output

or:

agent.run(refinement_text)

without also sending structured original constraints.

Replace it conceptually with:

state["effective_intent"] = merge_intent(
    original_intent=state["original_intent"],
    refinement=state["refinement_delta"]
)

Then send:

state["effective_intent"]

to query generation.

After that, add the intent-preservation validator before execution.

⸻

Important Design Principle

Conversation history should not be the primary mechanism for preserving these constraints.

Session history is useful for conversational continuity, but information such as:

Elzonris
Krystexxa
program
time period
claim count

is part of the query specification.

It should therefore live in structured application state.

Do not depend on the LLM rereading conversation history and correctly reconstructing those values every time.

Use:

Conversation History
        +
Structured Query State

rather than:

Conversation History Only

⸻

Final Recommended Solution

The strongest fix is therefore:

1. Parse the original question into structured intent.
2. Store explicit user constraints separately and preserve them.
3. Treat refinement as a delta, not a replacement request.
4. Merge refinement into original intent using field-level precedence.
5. Treat named drugs as filters, not merely grouping information.
6. Disable automatic Top-N behaviour when explicit entities exist.
7. Validate intent preservation before query generation.
8. Validate the query plan against effective intent.
9. Validate structured execution results against an answer contract.
10. Validate the final response before returning it.
11. Ask for clarification when required program/time-period context
    cannot be resolved.
12. Trace every transformation so the first stage that loses a
    constraint is immediately visible.

The key rule for the entire system should be:

Refinement may clarify, narrow, or explicitly modify a user’s request, but it must never silently broaden the request or discard an explicit user constraint.

