pip install sqlglot psycopg[binary] psycopg_pool

-------------

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

import sqlglot
from sqlglot import exp


DISALLOWED_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT",
    "CREATE", "ALTER", "DROP", "TRUNCATE",
    "GRANT", "REVOKE",
    "COPY", "CALL", "DO", "EXECUTE",
    "SET", "RESET",
}


@dataclass(frozen=True)
class SqlValidationResult:
    ok: bool
    reason: str
    referenced_tables: Tuple[str, ...] = ()


class ReadOnlySqlValidator:
    """
    Validates that SQL is:
      - single statement
      - read-only (SELECT or WITH ... SELECT)
      - references only allowed tables (optional)
    """

    def __init__(self, allowed_tables: Optional[Set[str]] = None):
        self.allowed_tables = set(allowed_tables or [])

    def validate(self, sql: str) -> SqlValidationResult:
        sql = (sql or "").strip()
        if not sql:
            return SqlValidationResult(ok=False, reason="Empty SQL")

        # Reject multiple statements early
        # sqlglot can parse multiple statements; we enforce exactly one.
        try:
            statements = sqlglot.parse(sql, read="postgres")
        except Exception as e:
            return SqlValidationResult(ok=False, reason=f"SQL parse failed: {e}")

        if len(statements) != 1:
            return SqlValidationResult(ok=False, reason="Only a single SQL statement is allowed")

        stmt = statements[0]

        # Enforce statement type: allow SELECT and WITH (CTE)
        if not isinstance(stmt, (exp.Select, exp.With, exp.Union, exp.Paren)):
            # Some SELECT forms parse as Union/Paren; we’ll still validate content below
            pass

        # Hard keyword deny-list check (defense-in-depth)
        upper_sql = sql.upper()
        for kw in DISALLOWED_KEYWORDS:
            if kw in upper_sql:
                return SqlValidationResult(ok=False, reason=f"Disallowed keyword detected: {kw}")

        # Ensure the AST contains a SELECT somewhere as the "main" action
        if not stmt.find(exp.Select):
            return SqlValidationResult(ok=False, reason="Only SELECT queries are allowed")

        # Extract referenced tables from AST
        tables = []
        for t in stmt.find_all(exp.Table):
            # exp.Table.this might contain table name, exp.Table.db schema
            name = t.name
            schema = (t.db or "").strip()
            if schema:
                tables.append(f"{schema}.{name}")
            else:
                # If schema missing, keep as name; your policy can reject schema-less refs
                tables.append(name)

        unique_tables = tuple(sorted(set(tables)))

        # If allowed_tables configured: enforce all referenced tables are in allowed set.
        if self.allowed_tables:
            # Strict mode: schema.table must match exactly
            for tbl in unique_tables:
                if tbl not in self.allowed_tables:
                    return SqlValidationResult(
                        ok=False,
                        reason=f"SQL references non-allowed table: {tbl}",
                        referenced_tables=unique_tables,
                    )

        return SqlValidationResult(ok=True, reason="OK", referenced_tables=unique_tables)
