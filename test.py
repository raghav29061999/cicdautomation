from __future__ import annotations

import re
from typing import Optional

from agno.tools.postgres import PostgresTools
from agno.utils.log import log_debug, log_error


# Keywords / patterns we never want to allow in "read-only" mode.
# Notes:
# - We block SELECT INTO explicitly (Postgres writes a new table)
# - We block COPY, CALL, DO, EXECUTE (can run server-side code / write)
# - We block DDL/DML and privilege changes
# - We block transaction control to avoid oddities (optional; safe default)
_FORBIDDEN_KEYWORDS = (
    "insert", "update", "delete", "merge", "upsert",
    "create", "alter", "drop", "truncate",
    "copy", "call", "do", "execute",
    "grant", "revoke",
    "vacuum", "analyze",
    "refresh",  # materialized view refresh can be write-ish
    "set", "reset",  # optional; remove if you need SET LOCAL, etc.
    "begin", "commit", "rollback", "savepoint", "release",
)

# Basic: must begin with SELECT or WITH
_ALLOWED_START = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

# Detect SELECT INTO (write)
_SELECT_INTO = re.compile(r"\bselect\b[\s\S]*?\binto\b", re.IGNORECASE)

# Word-boundary keyword matcher (applied after stripping comments/strings)
_FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _FORBIDDEN_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def _strip_sql_comments_and_strings(sql: str) -> str:
    """
    Remove:
      - single-line comments: -- ...
      - block comments: /* ... */
      - single-quoted strings: '...'
      - dollar-quoted strings: $$...$$ or $tag$...$tag$

    Goal: keyword scanning should ignore content inside strings/comments.
    This is not a full SQL parser, but it's robust enough for enforcement.
    """
    s = sql or ""

    # Remove block comments
    s = re.sub(r"/\*[\s\S]*?\*/", " ", s)

    # Remove single-line comments
    s = re.sub(r"--[^\n]*", " ", s)

    # Remove dollar-quoted strings: $tag$ ... $tag$
    # This handles $$...$$ too (tag can be empty).
    def _dq_replacer(match: re.Match) -> str:
        return " "

    s = re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$[\s\S]*?\$\1\$", _dq_replacer, s)

    # Remove single-quoted strings (handles escaped '' inside)
    s = re.sub(r"'([^']|'')*'", " ", s)

    return s


def _has_multiple_statements(sql: str) -> bool:
    """
    Disallow multi-statement queries.
    We treat any semicolon that isn't just a trailing terminator as suspicious.
    """
    s = (sql or "").strip()
    if not s:
        return False

    # Remove trailing semicolons/spaces
    s2 = re.sub(r"[;\s]+$", "", s)

    # Any remaining semicolon means multiple statements or statement chaining
    return ";" in s2


def validate_read_only_sql(sql: str) -> Optional[str]:
    """
    Returns:
      None if SQL is allowed
      error_message string if rejected
    """
    raw = (sql or "").strip()
    if not raw:
        return "Empty SQL is not allowed."

    if not _ALLOWED_START.match(raw):
        return "Only read-only SELECT/WITH queries are allowed."

    # Strip strings/comments for keyword checks
    cleaned = _strip_sql_comments_and_strings(raw)

    # Disallow multiple statements
    if _has_multiple_statements(cleaned):
        return "Multiple SQL statements are not allowed."

    # Disallow SELECT INTO
    if _SELECT_INTO.search(cleaned):
        return "SELECT INTO is not allowed (it writes a table)."

    # Disallow forbidden keywords
    m = _FORBIDDEN_RE.search(cleaned)
    if m:
        return f"Forbidden operation detected: '{m.group(1)}'"

    return None


class SafePostgresTools(PostgresTools):
    """
    Agno-native, production-safe PostgresTools:
    - Does NOT modify agno.tools.postgres.PostgresTools
    - Overrides only the entrypoints that accept arbitrary SQL from LLM/user
    """

    def run_query(self, query: str) -> str:
        err = validate_read_only_sql(query)
        if err:
            log_error(f"Read-only SQL policy violation: {err}")
            log_debug(f"Rejected SQL: {query}")
            return f"ERROR: Read-only SQL policy violation. {err}"

        return super().run_query(query)

    def inspect_query(self, query: str) -> str:
        """
        EXPLAIN is read-only, but we still validate the underlying query,
        because EXPLAIN <dangerous statement> can still be problematic.
        """
        err = validate_read_only_sql(query)
        if err:
            log_error(f"Read-only SQL policy violation (inspect): {err}")
            log_debug(f"Rejected SQL (inspect): {query}")
            return f"ERROR: Read-only SQL policy violation. {err}"

        return super().inspect_query(query)

-------------------------------------------------------------------------------------------

from src.tools.safe_postgres_tools import SafePostgresTools

def get_postgrestools():
    return SafePostgresTools(
        host=...,
        port=...,
        db_name=...,
        user=...,
        password=...,
        # keep your schema if you pass it
        table_schema="public",
    )
