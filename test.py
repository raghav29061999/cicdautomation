from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from src.tools.sql.readonly_validator import ReadOnlySqlValidator, SqlValidationResult


@dataclass(frozen=True)
class QueryResult:
    columns: Sequence[str]
    rows: List[Dict[str, Any]]
    validation: SqlValidationResult


class SafePostgresReadOnlyExecutor:
    """
    A hardened execution layer:
      - Validates SQL (read-only, single statement, allowed tables)
      - Runs with transaction_read_only=on
      - Applies statement timeout and row limit
      - Uses pooling
    """

    def __init__(
        self,
        dsn: str,
        allowed_tables: Optional[Set[str]] = None,
        statement_timeout_ms: int = 15_000,
        max_rows: int = 200,
        pool_min_size: int = 1,
        pool_max_size: int = 5,
    ):
        self._pool = ConnectionPool(
            conninfo=dsn,
            min_size=pool_min_size,
            max_size=pool_max_size,
            kwargs={"row_factory": dict_row},
        )
        self._validator = ReadOnlySqlValidator(allowed_tables=allowed_tables or set())
        self._timeout_ms = int(statement_timeout_ms)
        self._max_rows = int(max_rows)

    def close(self) -> None:
        self._pool.close()

    def run(self, sql: str) -> QueryResult:
        validation = self._validator.validate(sql)
        if not validation.ok:
            return QueryResult(columns=(), rows=[], validation=validation)

        # Enforce a hard row cap if not already present:
        # This is conservative: append LIMIT if the query doesn't have one.
        sql_limited = self._ensure_limit(sql, self._max_rows)

        with self._pool.connection() as conn:
            # Per-transaction settings
            with conn.cursor() as cur:
                cur.execute("BEGIN;")
                # Absolute safety: read-only transaction + timeout
                cur.execute("SET LOCAL transaction_read_only = on;")
                cur.execute(f"SET LOCAL statement_timeout = {self._timeout_ms};")

                cur.execute(sql_limited)
                rows = cur.fetchall()
                cols = [d.name for d in cur.description] if cur.description else []
                cur.execute("ROLLBACK;")

        return QueryResult(columns=cols, rows=rows, validation=validation)

    @staticmethod
    def _ensure_limit(sql: str, max_rows: int) -> str:
        upper = sql.upper()
        if " LIMIT " in upper:
            return sql
        # Avoid breaking trailing semicolons
        s = sql.rstrip().rstrip(";")
        return f"{s} LIMIT {max_rows};"
