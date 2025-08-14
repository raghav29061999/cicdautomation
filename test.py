SEED_SPEC_FUNC_BETTER = {
    # Ambiguous + Redundant
    "Ambiguous/Redundant Code": [
        "ambiguous column", "ambiguous reference", "ambiguous naming", "unclear name",
        "unclear reference", "confusing mapping", "duplicate code", "redundant code",
        "unnecessary code", "repeated logic", "shadowed variable", "unused variable", "unused import"
    ],

    # Commented-out
    "Commented-Out Code Present": [
        "commented out code", "commented code block", "commented block contains logic",
        "commented business logic", "dead code", "disabled code", "leftover code",
        "temporary commented", "debug code commented", "TODO commented"
    ],

    # Hardcoded values
    "Hardcoded Values": [
        "hardcoded value", "hard-coded value", "magic number", "literal value",
        "inline constant", "fixed value", "static value",
        "hardcoded file path", "hardcoded path", "absolute path",
        "hardcoded column name", "hardcoded dataset name", "hardcoded url",
        "inline config", "env value in code"
    ],

    # Merged quality problems
    "Incomplete/Incorrect/Inconsistent Implementation": [
        # incomplete / missing
        "incomplete code", "incomplete implementation", "partial implementation",
        "placeholder function", "stub function", "todo not implemented",
        "lack of data filtering", "missing filter", "no error handling", "no exception handling",
        "no data processing", "no transformation", "missing validation",
        # incorrect
        "incorrect calculation", "wrong calculation", "calculation is incorrect",
        "incorrect mapping", "wrong mapping", "incorrect conversion", "incorrect cast",
        "incorrect logic", "incorrect handling", "off by one",
        # inconsistent
        "inconsistent column naming", "inconsistent naming", "inconsistent data types",
        "inconsistent dtype", "inconsistent path handling", "mismatched schema", "type mismatch",
        # assumptions/calcs
        "incorrect assumption", "assumes without validation", "assumption not valid",
        "uses default without check"
    ],

    # Inefficient (non-query)
    "Inefficient Implementation": [
        "inefficient computation", "inefficient processing", "inefficient retrieval",
        "inefficient sorting", "inefficient archiving", "inefficient deduplication",
        "suboptimal performance", "not optimized", "slow loop", "nested loop",
        "row by row processing", "non vectorized", "brute force", "high time complexity",
        "o(n^2) complexity", "recomputes repeatedly", "multiple complex conditions"
    ],

    # Inefficient (query-specific)
    "Inefficient Query": [
        "inefficient query", "inefficient subquery", "slow query", "expensive query",
        "full table scan", "table scan", "missing index", "no index used",
        "select *", "cartesian join", "cross join", "n+1 query", "poor cardinality",
        "unfiltered join", "no where clause", "no partition pruning", "no predicate pushdown",
        "no limit", "no group by needed", "bad join order", "skewed join", "excessive shuffles"
    ],

    # Potential risks/issues (aiming for high recall)
    "Potential Risks/Issues": [
        "potential issue", "potential data loss", "potential null values",
        "potential performance issue", "potential rounding issue", "possible overflow",
        "possible precision loss", "possible truncation",
        "may return large dataset", "may return null", "may not handle edge cases",
        "might fail on edge cases", "could lead to error", "could result in failure",
        "risk of timeout", "risk of deadlock", "risk of memory leak",
        "likely to fail", "susceptible to error", "prone to failure"
    ],
}
