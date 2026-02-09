# Data Quality Checks

- Perform systematic data quality validations before any downstream or anomaly analysis.
  Treat these checks as mandatory gating conditions.

- Completeness Checks:
  - Identify missing or NULL values at column level.
  - Compute NULL percentage per column and flag threshold breaches.
  - Detect incomplete records based on required field sets.
  - Compare expected vs actual record counts for a given time window, entity, or source.

- Consistency Checks:
  - Validate cross-table referential integrity (foreign key relationships, orphan records).
  - Detect data type violations and incompatible value casts.
  - Identify format inconsistencies (dates, identifiers, codes, enums).
  - Detect duplicate records across natural keys or defined uniqueness rules.

- Accuracy Checks:
  - Validate numeric and categorical values against allowed ranges and domains.
  - Apply deterministic business rule validations where explicitly defined.
  - Detect deviations from established historical patterns or baselines.
  - Verify aggregate consistency (e.g., totals, balances, derived fields).

- Timeliness Checks:
  - Monitor data freshness based on update or ingestion timestamps.
  - Analyze expected vs actual data arrival frequency.
  - Detect lag or misalignment across related tables or pipelines.
  - Identify stale records that exceed acceptable age thresholds.

- Uniqueness Checks:
  - Validate primary key integrity and non-null enforcement.
  - Detect duplicate records violating uniqueness constraints.
  - Monitor drift in uniqueness assumptions over time.
--------------------------
    # Issue Categorization

- Categorize all detected issues by severity to support prioritization and decision-making.

- Blocking:
  - Issues that prevent reliable analysis or downstream processing.
  - Examples include missing primary keys, broken referential integrity, or critical data absence.

- Warning:
  - Issues that may degrade accuracy or confidence but do not fully block usage.
  - Examples include partial completeness issues, delayed updates, or minor inconsistencies.

- Advisory:
  - Issues representing best-practice violations or optimization opportunities.
  - Examples include suboptimal formats, soft constraints, or non-critical deviations.
