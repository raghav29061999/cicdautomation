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


REGEX_BOOSTS_FUNC_BETTER = {
    "Ambiguous/Redundant Code": [
        r"\bambig(?:u|)ous\b", r"\bambig(?:u|)ous\s+(?:col(?:umn)?|name|ref(?:erence)?)\b",
        r"\bredundan(?:t|cy)\b", r"\bduplicate\s+code\b", r"\bunused\s+(?:var|variable|import)\b",
        r"\bshadow(?:ed|ing)\s+var"
    ],

    "Commented-Out Code Present": [
        r"\bcommented[-\s]?out\b", r"\bcommented\s+code\b", r"\bcommented\s+block\b",
        r"\bdead\s+code\b", r"\bdisabled\s+code\b", r"\bcommented.*logic\b"
    ],

    "Hardcoded Values": [
        r"\bhard[-\s]?cod(?:e|ed)\b", r"\bmagic\s+number\b", r"\bliteral\s+value\b|\binline\s+constant\b",
        r"\bhardcoded\s+(?:file|path|url|column|dataset|name)s?\b", r"\babsolute\s+path\b"
    ],

    "Incomplete/Incorrect/Inconsistent Implementation": [
        r"\bincomplete\b|\bpartial\s+implementation\b|\bnot\s+implemented\b|\bplaceholder\b|\bstub\b",
        r"\black\s+of\s+data\s+filter(?:ing)?\b|\bmissing\s+filter\b",
        r"\bno\s+(?:error|exception)\s+handling\b|\bno\s+(?:data\s+processing|transformation)\b",
        r"\bincorrect\s+calculat\w*\b|\bcalculat\w*\s+(?:is|are)\s+incorrect\b",
        r"\bincorrect\s+(?:mapping|conversion|cast|logic|handling)\b|\bwrong\s+(?:calc|mapping)\b",
        r"\binconsistent\b|\bmismatch(?:ed)?\s+(?:type|schema)\b|\btype\s+mismatch\b",
        r"\bincorrect\s+assumption\b|\bassumes\b"
    ],

    "Inefficient Implementation": [
        r"^\s*inefficient\b", r"\bsuboptimal\b|\bnot\s+optimized\b",
        r"\bnon[-\s]?vectori[sz]ed\b|\brow[-\s]?by[-\s]?row\b|\bnested\s+loop\b|\bslow\s+loop\b",
        r"\bo\(?n\^?2\)?\b|\bo\(\s*n\s*\^\s*2\s*\)\b", r"\brecompute[s]?\s+repeatedly\b"
    ],

    "Inefficient Query": [
        r"\binefficient\s+(?:query|subquery)\b", r"\bslow\s+query\b|\bexpensive\s+query\b",
        r"\bfull\s+table\s+scan\b|\btable\s+scan\b", r"\bmissing\s+index\b|\bno\s+index\b",
        r"\bselect\s*\*\b", r"\b(cartesian|cross)\s+join\b", r"\bn\+1\s+query\b",
        r"\bno\s+where\b|\bno\s+filter\b|\bno\s+limit\b",
        r"\bno\s+partition\s+(?:pruning|filter)\b|\bno\s+predicate\s+pushdown\b",
        r"\bbad\s+join\s+order\b|\bskewed\s+join\b|\bexcessive\s+shuffle"
    ],

    # Heavily expanded Potential patterns
    "Potential Risks/Issues": [
        r"^\s*potential(?:ly)?\b",
        r"\bpotential\s+(?:issue|risk|data\s+loss|null\s+values?|performance|rounding|overflow|precision|truncation|timeout|deadlock|leak)\b",
        r"\b(?:risk|risk\s+of)\b",
        r"\b(?:may|might|could|can)\s+(?:cause|lead|result|return|fail)\b",
        r"\bmay\s+return\s+large\s+data(?:set|s)?\b|\bmay\s+return\s+null\b",
        r"\bedge\s*cases?\s*(?:not\s*handled|unhandled|missing)\b",
        r"\b(?:does|do)\s+not\s+handle\s+edge\s*cases\b|\bmay\s*not\s+handle\b",
        r"\bpossible\b|\bpossibly\b|\blikely\b|\bprone\s+to\b|\bsusceptible\s+to\b"
    ],
}


df_functional_labeled = assign_issue_names_with_clouds(
    functional_df,
    seed_spec=SEED_SPEC_FUNC_BETTER,
    noissue_config=NOISSUE_CONFIG_FUNC,     # with stronger exclusions applied
    text_col="DESCRIPTION",
    sim_threshold=0.13,                     # a bit looser
    ngram_range=(1, 3),                     # broader phrase coverage
    use_char_ngrams=True,                   # typo robustness (e.g., “potental”, “ambigous”)
    token_pattern=r"(?u)\b[\w\./+\-*=:%]+\b",
    regex_boosts=REGEX_BOOSTS_FUNC_BETTER,
    boost_weight=0.45,                      # strong nudge toward matches
    force_on_regex=False,                   # keep global False
)

# Optional: guarantee Potential when regex hits (only for this label)
_pats = [re.compile(p, re.I) for p in REGEX_BOOSTS_FUNC_BETTER["Potential Risks/Issues"]]
mask_potential = functional_df["DESCRIPTION"].fillna("").str.lower().map(lambda s: any(p.search(s) for p in _pats))
df_functional_labeled.loc[mask_potential, "ISSUE_NAME"] = "Potential Risks/Issues"

# Check counts
print(df_functional_labeled["ISSUE_NAME"].value_counts(dropna=False))

