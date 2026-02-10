from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from agno.tools.toolkit import Toolkit
from agno.tools.postgres import PostgresTools


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _md_table(rows: List[Dict[str, Any]], max_rows: int = 25) -> str:
    """
    Render query results (list of dict rows) as a Markdown table.

    Args:
        rows: List of rows where each row is a dict of {column_name: value}.
        max_rows: Maximum number of rows to render to keep outputs lightweight.

    Returns:
        Markdown table as a string. If no rows are present, returns "_No rows returned._".
    """
    if not rows:
        return "_No rows returned._"

    rows = rows[:max_rows]
    cols = list(rows[0].keys())

    def fmt(v: Any) -> str:
        if v is None:
            return "NULL"
        s = str(v).replace("\n", " ").strip()
        return s[:300] + ("…" if len(s) > 300 else "")

    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    body = "\n".join("| " + " | ".join(fmt(r.get(c)) for c in cols) + " |" for r in rows)
    return "\n".join([header, sep, body])


def _validate_identifier(name: str, kind: str) -> None:
    """
    Validate that an SQL identifier (schema/table/column) is safe.

    Allows only letters, digits, and underscores, disallowing leading digits.
    This prevents SQL injection via identifiers.

    Args:
        name: Identifier to validate.
        kind: "schema" | "table" | "column" (used for error messages).

    Raises:
        ValueError: If the identifier is not valid.
    """
    if not _IDENTIFIER_RE.match(name or ""):
        raise ValueError(f"Invalid {kind} identifier: {name!r}")


def _qualify(schema: str, table: str) -> str:
    """
    Build a qualified name `schema.table` after validating both parts.

    Args:
        schema: Schema name.
        table: Table name.

    Returns:
        Qualified name as "schema.table".
    """
    _validate_identifier(schema, "schema")
    _validate_identifier(table, "table")
    return f"{schema}.{table}"


def _is_read_only_sql(sql: str) -> bool:
    """
    Hard guard: allow only read-only SELECT queries.

    Rules:
    - Query must start with SELECT or WITH (CTE leading to SELECT).
    - Query must not contain write/DDL keywords anywhere.

    Args:
        sql: Raw SQL string.

    Returns:
        True if the SQL is considered read-only, else False.
    """
    s = (sql or "").strip().lower()
    if not s:
        return False
    if s.startswith("select") or s.startswith("with"):
        banned = ["insert", "update", "delete", "truncate", "alter", "drop", "merge", "create", "grant", "revoke"]
        return not any(re.search(rf"\b{kw}\b", s) for kw in banned)
    return False


@dataclass(frozen=True)
class QualityThresholds:
    """
    Optional thresholds you can use later for scoring/severity decisions.

    Note: The current toolkit returns raw check results; severity scoring can be
    layered on top elsewhere if you want.
    """
    null_pct_blocking: float = 0.30
    null_pct_warning: float = 0.10
    duplicates_blocking: int = 1
    staleness_warning_hours: int = 24
    staleness_blocking_hours: int = 72


class DataQualityTools(Toolkit):
    """
    Deterministic Data Quality & Integrity toolkit over PostgreSQL using Agno PostgresTools.

    This toolkit is intentionally instruction-free at initialization time so that
    you can supply all behavioral instructions at the Agent level.

    Design goals:
    - Read-only access: never modifies database state.
    - Safe execution: blocks non-SELECT statements and validates identifiers.
    - Workflow-friendly outputs: returns compact Markdown tables.
    """

    def __init__(
        self,
        postgres: PostgresTools,
        *,
        allowed_schemas: Sequence[str] = ("public",),
        thresholds: QualityThresholds = QualityThresholds(),
        **kwargs: Any,
    ):
        self.pg = postgres
        self.allowed_schemas = tuple(allowed_schemas)
        self.thresholds = thresholds

        tools = [
            self.list_tables,
            self.describe_table,
            self.table_row_count,
            self.null_profile,
            self.duplicate_check,
            self.pk_null_check,
            self.fk_orphan_check,
            self.freshness_check,
            self.daily_health_snapshot,
        ]

        # No instructions here; keep the toolkit "pure" and let the Agent carry instructions.
        super().__init__(
            name="data_quality_tools",
            tools=tools,
            **kwargs,
        )

    def list_tables(self, schema: str = "public") -> str:
        """
        List tables in an allowed schema.

        Use this to discover candidate tables for validation or to confirm table names.

        Args:
            schema: Schema name. Must be in allowed_schemas.

        Returns:
            Markdown table with a single column: `table`.
        """
        self._enforce_schema(schema)
        tables = self.pg.show_tables()
        return _md_table([{"table": t} for t in (tables or [])])

    def describe_table(self, table: str, schema: str = "public") -> str:
        """
        Describe a table's columns and metadata (types, nullability, etc.).

        Use this before defining checks to:
        - confirm column names and types
        - decide required vs optional fields

        Args:
            table: Table name (unqualified). Must be a valid identifier.
            schema: Schema name. Must be in allowed_schemas.

        Returns:
            Markdown table describing the table schema/columns.
        """
        self._enforce_schema(schema)
        _validate_identifier(table, "table")
        desc = self.pg.describe_table(table=table)
        return _md_table(desc if isinstance(desc, list) else [{"description": desc}])

    def table_row_count(self, table: str, schema: str = "public") -> str:
        """
        Compute total row count for a table.

        Useful for:
        - baseline monitoring
        - validating expected vs actual row volumes

        Args:
            table: Table name.
            schema: Schema name.

        Returns:
            Markdown table with one row: `row_count`.
        """
        self._enforce_schema(schema)
        qname = _qualify(schema, table)
        sql = f"SELECT COUNT(*) AS row_count FROM {qname};"
        return self._run_md(sql)

    def null_profile(self, table: str, columns: Sequence[str], schema: str = "public") -> str:
        """
        Completeness check: compute NULL count and NULL percentage per column.

        Notes:
        - Columns must be explicitly provided (no SELECT *).
        - Output sorted by highest NULL% first.

        Args:
            table: Table name.
            columns: Column names to profile.
            schema: Schema name.

        Returns:
            Markdown table with:
            - column_name
            - null_count
            - total_count
            - null_pct
        """
        self._enforce_schema(schema)
        qname = _qualify(schema, table)

        cols = []
        for c in columns:
            _validate_identifier(c, "column")
            cols.append(c)

        if not cols:
            return "_No columns provided._"

        unions = []
        for c in cols:
            unions.append(
                f"""
                SELECT
                  '{c}' AS column_name,
                  SUM(CASE WHEN {c} IS NULL THEN 1 ELSE 0 END) AS null_count,
                  COUNT(*) AS total_count,
                  ROUND(
                    (SUM(CASE WHEN {c} IS NULL THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*),0)) * 100,
                    2
                  ) AS null_pct
                FROM {qname}
                """
            )
        sql = " UNION ALL ".join(unions) + " ORDER BY null_pct DESC, null_count DESC;"
        return self._run_md(sql)

    def duplicate_check(self, table: str, key_columns: Sequence[str], schema: str = "public", top_n: int = 25) -> str:
        """
        Uniqueness check: find duplicates by a provided natural/compound key.

        Use this when:
        - primary key is unknown or not enforced
        - validating uniqueness assumptions for business keys

        Args:
            table: Table name.
            key_columns: Columns that together should be unique.
            schema: Schema name.
            top_n: Maximum duplicate groups to return.

        Returns:
            Markdown table of duplicate key groups with:
            - key columns
            - dup_count
        """
        self._enforce_schema(schema)
        qname = _qualify(schema, table)

        keys = []
        for c in key_columns:
            _validate_identifier(c, "column")
            keys.append(c)
        if not keys:
            return "_No key columns provided._"

        key_expr = ", ".join(keys)
        sql = f"""
        SELECT {key_expr}, COUNT(*) AS dup_count
        FROM {qname}
        GROUP BY {key_expr}
        HAVING COUNT(*) > 1
        ORDER BY dup_count DESC
        LIMIT {int(top_n)};
        """
        return self._run_md(sql)

    def pk_null_check(self, table: str, pk_column: str, schema: str = "public") -> str:
        """
        Primary key integrity check: count NULLs in the PK column.

        If PK has NULLs, joins and entity tracking can be unreliable.

        Args:
            table: Table name.
            pk_column: Primary key column name.
            schema: Schema name.

        Returns:
            Markdown table with:
            - total_rows
            - pk_null_rows
        """
        self._enforce_schema(schema)
        qname = _qualify(schema, table)
        _validate_identifier(pk_column, "column")

        sql = f"""
        SELECT
          COUNT(*) AS total_rows,
          SUM(CASE WHEN {pk_column} IS NULL THEN 1 ELSE 0 END) AS pk_null_rows
        FROM {qname};
        """
        return self._run_md(sql)

    def fk_orphan_check(
        self,
        child_table: str,
        child_fk_column: str,
        parent_table: str,
        parent_pk_column: str,
        schema: str = "public",
        top_n: int = 25,
    ) -> str:
        """
        Consistency check: detect orphan foreign keys.

        Finds values where:
        - child FK is NOT NULL
        - but no corresponding parent PK exists

        Args:
            child_table: Child table name.
            child_fk_column: Foreign key column in child table.
            parent_table: Parent table name.
            parent_pk_column: Primary key column in parent table.
            schema: Schema name.
            top_n: Max orphan FK values to return.

        Returns:
            Markdown table with:
            - orphan_fk_value
            - orphan_rows
        """
        self._enforce_schema(schema)
        child = _qualify(schema, child_table)
        parent = _qualify(schema, parent_table)

        for c in [child_fk_column, parent_pk_column]:
            _validate_identifier(c, "column")

        sql = f"""
        SELECT c.{child_fk_column} AS orphan_fk_value, COUNT(*) AS orphan_rows
        FROM {child} c
        LEFT JOIN {parent} p
          ON c.{child_fk_column} = p.{parent_pk_column}
        WHERE c.{child_fk_column} IS NOT NULL
          AND p.{parent_pk_column} IS NULL
        GROUP BY c.{child_fk_column}
        ORDER BY orphan_rows DESC
        LIMIT {int(top_n)};
        """
        return self._run_md(sql)

    def freshness_check(self, table: str, timestamp_column: str, schema: str = "public") -> str:
        """
        Timeliness check: compute latest timestamp and staleness in hours.

        Use this to detect stale tables or lagging ingestion.

        Args:
            table: Table name.
            timestamp_column: Column representing last update/ingestion time.
            schema: Schema name.

        Returns:
            Markdown table with:
            - latest_ts
            - staleness_hours
        """
        self._enforce_schema(schema)
        qname = _qualify(schema, table)
        _validate_identifier(timestamp_column, "column")

        sql = f"""
        SELECT
          MAX({timestamp_column}) AS latest_ts,
          EXTRACT(EPOCH FROM (NOW() - MAX({timestamp_column}))) / 3600.0 AS staleness_hours
        FROM {qname};
        """
        return self._run_md(sql)

    def daily_health_snapshot(
        self,
        tables: Sequence[str],
        schema: str = "public",
        freshness_column: Optional[str] = None,
        top_n: int = 10,
    ) -> str:
        """
        On-demand health snapshot across multiple tables.

        Produces a lightweight summary intended for "daily health check" workflows
        (even when invoked interactively):
        - row_count per table
        - optional latest timestamp + staleness hours (if freshness_column is provided)

        Important:
        - This does NOT schedule itself.
        - It reports what the database shows at query time.

        Args:
            tables: Table names to include.
            schema: Schema name.
            freshness_column: If provided, compute staleness using this timestamp column.
            top_n: Max rows to render.

        Returns:
            Markdown table with:
            - table
            - row_count
            - latest_ts (optional)
            - staleness_hours (optional)
        """
        self._enforce_schema(schema)
        rows: List[Dict[str, Any]] = []

        for t in tables:
            _validate_identifier(t, "table")
            qname = _qualify(schema, t)

            rc = self._run_raw(f"SELECT COUNT(*) AS row_count FROM {qname};")
            row_count = (rc[0].get("row_count") if rc else None)

            staleness = None
            latest_ts = None
            if freshness_column:
                _validate_identifier(freshness_column, "column")
                fr = self._run_raw(
                    f"""
                    SELECT
                      MAX({freshness_column}) AS latest_ts,
                      EXTRACT(EPOCH FROM (NOW() - MAX({freshness_column}))) / 3600.0 AS staleness_hours
                    FROM {qname};
                    """
                )
                if fr:
                    latest_ts = fr[0].get("latest_ts")
                    staleness = fr[0].get("staleness_hours")

            rows.append(
                {
                    "table": qname,
                    "row_count": row_count,
                    "latest_ts": latest_ts,
                    "staleness_hours": None if staleness is None else round(float(staleness), 2),
                }
            )

        if freshness_column:
            rows.sort(key=lambda r: (r["staleness_hours"] is None, r["staleness_hours"]), reverse=True)

        return _md_table(rows[: int(top_n)])

    # -------------------------
    # Internals
    # -------------------------

    def _enforce_schema(self, schema: str) -> None:
        """Allowlist enforcement: only approved schemas may be queried."""
        _validate_identifier(schema, "schema")
        if schema not in self.allowed_schemas:
            raise PermissionError(f"Schema {schema!r} not in allowed_schemas={self.allowed_schemas!r}")

    def _run_md(self, sql: str) -> str:
        """Execute a read-only SQL query and return a Markdown table."""
        rows = self._run_raw(sql)
        return _md_table(rows)

    def _run_raw(self, sql: str) -> List[Dict[str, Any]]:
        """
        Execute a read-only SQL query and return results as list[dict].

        Safety:
        - Blocks non-SELECT/CTE queries using _is_read_only_sql.
        - Uses PostgresTools.run_query for execution.

        Args:
            sql: SQL query string.

        Returns:
            List of dict rows (column -> value). Empty list if no results.

        Raises:
            PermissionError: If SQL is not read-only.
        """
        if not _is_read_only_sql(sql):
            raise PermissionError("Only read-only SELECT/CTE queries are allowed.")

        out = self.pg.run_query(query=sql)

        if out is None:
            return []
        if isinstance(out, list):
            return out
        if isinstance(out, dict):
            return [out]
        return [{"result": out}]
