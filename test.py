# Safety and SQL Constraints

- Operate in **strict read-only mode** at all times.
  Never perform INSERT, UPDATE, DELETE, TRUNCATE, MERGE, ALTER, DROP, or any schema-changing operations.

- Fetch **only the minimum required data** needed to perform a given validation or check.
  Avoid `SELECT *`; explicitly select required columns and apply restrictive WHERE clauses.

- Use **parameterized queries exclusively** for all dynamic values.
  Never interpolate variables directly into SQL strings.

- Query **only approved schemas, tables, and views**.
  Do not infer, discover, or access undocumented or unapproved database objects.

- Enforce **row-level and column-level access discipline**.
  Do not attempt to bypass database permissions or access controls.

- Prevent **raw PII exposure** in all outputs.
  Sensitive fields must be masked, anonymized, hashed, or aggregated before being surfaced in logs, reports, or responses.

- Do not persist query results, raw records, or intermediate datasets outside the execution context unless explicitly authorized.

- Prefer **aggregations, counts, distributions, and checksums** over row-level data inspection wherever possible.

- Apply **query safety limits**:
  Use LIMIT clauses where applicable, avoid unbounded scans, and be mindful of query cost and execution time.

- Assume the database may contain **incomplete, inconsistent, or partially updated data**.
  Never treat query results as ground truth without validation.

- Treat all database inputs as **untrusted**.
  Validate data types, ranges, and expected formats explicitly during analysis.

- Fail safely.
  If a query cannot be executed due to permission, schema, or safety constraints, report the limitation clearly instead of attempting workarounds.
