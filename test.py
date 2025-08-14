SEED_SPEC_FUNC = {
    # 1) Ambiguous + Redundant
    "Ambiguous/Redundant Code": [
        "redundant", "duplicate code", "ambiguous column", "ambiguous column reference",
        "ambiguous column name", "unclear naming", "unclear reference"
    ],
    # 2) Commented-out code (your ask to name this)
    "Commented-Out Code Present": [
        "commented out code", "commented code block", "commented block contains logic",
        "unfinished functionality commented", "dead code", "disabled code"
    ],
    # 3) Hardcoded values
    "Hardcoded Values": [
        "hardcoded column name", "hardcoded business number", "hardcoded dataset name",
        "hardcoded file path", "magic number", "constant value", "inline config", "literal value"
    ],
    # 4) Merged bucket: incomplete + incorrect + inconsistent (+ assumptions/calcs)
    "Incomplete/Incorrect/Inconsistent Implementation": [
        "incomplete code", "incomplete data", "incomplete implementation",
        "lack of data filtering", "no data filtering", "lack of error handling",
        "no error handling", "no data processing", "no transformation",
        "incorrect calculation", "incorrect column mapping", "incorrect conversion",
        "incorrect handling", "incorrect logic",
        "inconsistent column naming", "inconsistent data types", "inconsistent handling of path",
        "incorrect assumption", "assumes", "assumption not valid"
    ],
    # 5) Inefficient (keep separate)
    "Inefficient Implementation": [
        "inefficient computation", "inefficient data archiving", "inefficient deduplication",
        "inefficient processing", "inefficient retrieval", "inefficient sorting",
        "multiple complex conditions", "large number of operations", "suboptimal performance",
        "not optimized"
    ],
    # 6) Inefficient Query (query-specific)
    "Inefficient Query": [
        "inefficient query", "inefficient subquery", "subquery slow", "full table scan",
        "select *", "cartesian join", "missing index", "poor query performance", "n+1 query"
    ],
    # 7) Potential risks/issues
    "Potential Risks/Issues": [
        "potential data loss", "potential null values", "potential performance issue",
        "potential rounding issue", "may return large dataset", "could lead to", "might result in"
    ],
}


NOISSUE_FUNC_STRONG = [
    r"^\s*[-*]?\s*no\s+(apparent|known|major|significant)?\s*(functionalit(y|y\s+related)\s+)?issues?\s*(found|identified|detected|observed|reported)?\b",
    r"^\s*[-*]?\s*no\s+issues?\s+identified\b",
    r"^\s*[-*]?\s*no\s+functionality\s+issues?\s+identified\b",
    r"^\s*[-*]?\s*the\s+code\s+appears\s+to\s+(?:function|be\s*functional|be\s*functioning)\b",
]
NOISSUE_FUNC_SECONDARY = [
    r"\bno\s+(functionality\s+)?issues?\s*(found|identified|detected|observed|reported)?\b",
    r"\bappears\s+to\s+be\s+functional\b",
    r"\bappears\s+to\s+be\s+functioning\b",
]
NOISSUE_FUNC_EXCLUSIONS = r"\b(except|but|however|though|nevertheless|yet|still|apart\s+from|except\s+for)\b"

NOISSUE_CONFIG_FUNC = {
    "strong": NOISSUE_FUNC_STRONG,
    "secondary": NOISSUE_FUNC_SECONDARY,
    "exclusions": NOISSUE_FUNC_EXCLUSIONS,
}

df_functional_labeled = assign_issue_names_with_clouds(
    functional_df,
    SEED_SPEC_FUNC,
    NOISSUE_CONFIG_FUNC,
    text_col="DESCRIPTION",
    sim_threshold=0.15,     # lower to 0.12 if many fall into Unclustered
    ngram_range=(1, 2),     # try (1,3) for broader matching
    use_char_ngrams=False,  # True can help with short/code-y strings
    make_clouds=False       # True to render QA word clouds
)

print(df_functional_labeled["ISSUE_NAME"].value_counts(dropna=False))
# df_functional_labeled.to_parquet("functional_issue_names.parquet", index=False)


