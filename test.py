src/guardrails/insights/__init__.py
"""
Use of this file:
Expose Insights guardrail hooks so agent_5.py can import them cleanly from one place.
"""

from .pre_hooks import validate_insights_table_input
from .post_hooks import enforce_insights_output_contract

__all__ = [
    "validate_insights_table_input",
    "enforce_insights_output_contract",
]


-------------------------------------------------------------

src/guardrails/insights/exceptions.py
"""
Use of this file:
Define custom exceptions for Insights-specific guardrail failures.
This keeps error handling explicit and easier to debug.
"""


class InsightsGuardrailError(Exception):
    """Base exception for all Insights guardrail failures."""


class InvalidInsightsInputError(InsightsGuardrailError):
    """Raised when the incoming table input is missing, malformed, or unsafe."""


class InvalidInsightsOutputError(InsightsGuardrailError):
    """Raised when the generated insights output does not match the expected contract."""

---------------------------------------------------------------------------
src/guardrails/insights/validators.py
"""
Use of this file:
Contains pure helper/validation functions for Insights guardrails.
No Agno-specific wiring should live here.
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Sequence

from .exceptions import InvalidInsightsInputError, InvalidInsightsOutputError

# Accepts:
#   table_name
#   schema.table_name
# Does NOT accept:
#   spaces, semicolons, SQL fragments, comments, instructions
TABLE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")

# Not exhaustive, but enough to catch obvious abuse in a field that should only be a table identifier.
SUSPICIOUS_INPUT_PATTERNS = [
    r";",                # multiple statements / SQL chaining
    r"--",               # SQL comments
    r"/\*",              # SQL block comments
    r"\bselect\b",
    r"\binsert\b",
    r"\bupdate\b",
    r"\bdelete\b",
    r"\bdrop\b",
    r"\balter\b",
    r"\bcreate\b",
    r"\btruncate\b",
    r"\bunion\b",
    r"\bignore\b",
    r"\binstruction\b",
    r"\bsystem\b",
    r"\bprompt\b",
    r"\bjailbreak\b",
]

MAX_PROMPTS = 8
MIN_PROMPTS = 8
MAX_PROMPT_LENGTH = 180
MIN_PROMPT_LENGTH = 8


def extract_table_name(run_input: Any) -> str:
    """
    Extract table name from the incoming run_input.

    Supported shapes:
    - simple string: "schema.table"
    - dict-like: {"table_name": "..."} or {"table": "..."}
    - object-like: .table_name or .table

    Raise if not found.
    """
    if run_input is None:
        raise InvalidInsightsInputError("Insights input is missing.")

    if isinstance(run_input, str):
        table_name = run_input.strip()
        if not table_name:
            raise InvalidInsightsInputError("Insights input table name is empty.")
        return table_name

    if isinstance(run_input, dict):
        value = run_input.get("table_name") or run_input.get("table")
        if isinstance(value, str) and value.strip():
            return value.strip()
        raise InvalidInsightsInputError("Insights input must include 'table_name' or 'table'.")

    for attr in ("table_name", "table"):
        value = getattr(run_input, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    raise InvalidInsightsInputError("Could not extract table name from Insights input.")


def validate_table_identifier(table_name: str) -> None:
    """
    Validate that the table input is a strict identifier, not free text or SQL.
    """
    if not table_name:
        raise InvalidInsightsInputError("Table name is empty.")

    if len(table_name) > 128:
        raise InvalidInsightsInputError("Table name is too long to be a valid identifier.")

    if not TABLE_IDENTIFIER_RE.fullmatch(table_name):
        raise InvalidInsightsInputError(
            "Invalid table name format. Expected 'table_name' or 'schema.table_name'."
        )


def detect_suspicious_table_input(table_name: str) -> None:
    """
    Reject table_name values that look like SQL or prompt injection attempts.
    """
    lowered = table_name.lower()
    for pattern in SUSPICIOUS_INPUT_PATTERNS:
        if re.search(pattern, lowered):
            raise InvalidInsightsInputError(
                "Suspicious content detected in table input. Only a table identifier is allowed."
            )


def normalize_lines_to_prompts(content: str) -> List[str]:
    """
    Convert text output into a list of prompts.

    Handles common LLM formats like:
    - numbered lists
    - bullet lists
    - plain newline-separated items
    """
    if not content or not content.strip():
        return []

    lines = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Remove bullets / numbering prefixes like:
        # 1. text
        # - text
        # * text
        # 1) text
        line = re.sub(r"^\s*(?:[-*•]|\d+[\.\)])\s*", "", line).strip()
        if line:
            lines.append(line)

    return lines


def dedupe_prompts(prompts: Sequence[str]) -> List[str]:
    """
    Remove exact duplicates case-insensitively while preserving order.
    """
    seen = set()
    result: List[str] = []

    for prompt in prompts:
        key = " ".join(prompt.lower().split())
        if key not in seen:
            seen.add(key)
            result.append(prompt.strip())

    return result


def validate_prompt_text(prompt: str) -> None:
    """
    Validate a single prompt is UI-friendly and analytics-oriented enough.
    """
    if len(prompt) < MIN_PROMPT_LENGTH:
        raise InvalidInsightsOutputError(f"Prompt too short: {prompt!r}")

    if len(prompt) > MAX_PROMPT_LENGTH:
        raise InvalidInsightsOutputError(f"Prompt too long: {prompt!r}")

    lowered = prompt.lower()

    blocked_patterns = [
        r"\bselect\b",
        r"\binsert\b",
        r"\bupdate\b",
        r"\bdelete\b",
        r"\bdrop\b",
        r"\balter\b",
        r"\btruncate\b",
        r"```",              # no code block leakage
        r"\bsystem prompt\b",
        r"\binternal\b",
        r"\btool\b",
    ]

    for pattern in blocked_patterns:
        if re.search(pattern, lowered):
            raise InvalidInsightsOutputError(
                f"Prompt contains disallowed technical/system content: {prompt!r}"
            )


def parse_output_to_prompt_list(content: Any) -> List[str]:
    """
    Try to parse output content into a prompt list.

    Supports:
    - JSON list string
    - dict like {"prompts": [...]}
    - plain text block with one prompt per line
    """
    if content is None:
        raise InvalidInsightsOutputError("Insights output is empty.")

    if isinstance(content, list):
        prompts = [str(item).strip() for item in content if str(item).strip()]
        return dedupe_prompts(prompts)

    if isinstance(content, dict):
        raw_prompts = content.get("prompts")
        if isinstance(raw_prompts, list):
            prompts = [str(item).strip() for item in raw_prompts if str(item).strip()]
            return dedupe_prompts(prompts)

    if isinstance(content, str):
        text = content.strip()

        # Try JSON first
        try:
            loaded = json.loads(text)
            if isinstance(loaded, list):
                prompts = [str(item).strip() for item in loaded if str(item).strip()]
                return dedupe_prompts(prompts)
            if isinstance(loaded, dict) and isinstance(loaded.get("prompts"), list):
                prompts = [str(item).strip() for item in loaded["prompts"] if str(item).strip()]
                return dedupe_prompts(prompts)
        except Exception:
            pass

        return dedupe_prompts(normalize_lines_to_prompts(text))

    # Fallback
    text = str(content).strip()
    return dedupe_prompts(normalize_lines_to_prompts(text))


def validate_prompt_list(prompts: Sequence[str]) -> None:
    """
    Final contract check:
    - exactly 8 prompts
    - each prompt safe and UI-ready
    """
    if len(prompts) != MAX_PROMPTS:
        raise InvalidInsightsOutputError(
            f"Insights output must contain exactly {MAX_PROMPTS} prompts, got {len(prompts)}."
        )

    for prompt in prompts:
        validate_prompt_text(prompt)


def format_prompts_for_return(prompts: Sequence[str]) -> str:
    """
    Convert prompt list back into a stable newline-separated format.
    This is simple and UI-friendly if your API currently returns text.
    """
    return "\n".join(prompts)



-------------------------------------

src/guardrails/insights/pre_hooks.py
"""
Use of this file:
Agno pre-hooks for Insights Agent.
These run before the LLM executes and validate the incoming table identifier.
"""

from __future__ import annotations

from typing import Any, Optional

from .validators import (
    detect_suspicious_table_input,
    extract_table_name,
    validate_table_identifier,
)


def validate_insights_table_input(
    run_input: Any,
    session_state: Optional[dict] = None,
    **_: Any,
) -> None:
    """
    Pre-hook for Insights Agent.

    What it does:
    1. Extracts table name from incoming run_input
    2. Ensures it is a valid identifier
    3. Rejects suspicious SQL / prompt-injection-like content
    4. Stores validated table name in session_state for optional reuse/debugging

    Agno pre-hooks are designed for input validation before model execution.
    """
    table_name = extract_table_name(run_input)
    validate_table_identifier(table_name)
    detect_suspicious_table_input(table_name)

    if session_state is not None:
        session_state["validated_insights_table_name"] = table_name

--------------------------------------------------------------------
src/guardrails/insights/post_hooks.py

"""
Use of this file:
Agno post-hooks for Insights Agent.
These run after the model generates a response and enforce the Insights output contract.
"""

from __future__ import annotations

from typing import Any

from .validators import (
    format_prompts_for_return,
    parse_output_to_prompt_list,
    validate_prompt_list,
)


def enforce_insights_output_contract(run_output: Any, **_: Any) -> None:
    """
    Post-hook for Insights Agent.

    What it does:
    1. Reads run_output.content
    2. Parses it into a list of prompts
    3. Enforces exactly 8 safe prompts
    4. Rewrites output into a stable newline-separated format

    Agno post-hooks can validate and transform output before it is returned.
    """
    content = getattr(run_output, "content", None)
    prompts = parse_output_to_prompt_list(content)
    validate_prompt_list(prompts)

    # Normalize final response shape.
    run_output.content = format_prompts_for_return(prompts)

----------------------------------------------------------------------------------------------------
