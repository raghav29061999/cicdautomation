SEED_SPEC_COMPLEX = {
    # 1) Complexity of logic/structure
    "High/Overly Complex Logic & Structure": [
        "high complexity", "overly complex", "complex query", "complex logic",
        "nested calculations", "nested case statements", "nested conditional logic",
        "deep nesting", "nested queries", "nested subqueries", "complex join condition",
        "date calculation", "date manipulation", "lambda functions", "loops",
        "large number of conditions", "conditional logic", "complicated query structure"
    ],

    # 2) Excessive steps/functions/ops
    "Excessive Operations / Overuse of Functions": [
        "excessive conditional logic", "too many configuration params", "too many parameters",
        "excessive feature engineering", "excessive grouping", "excessive logging",
        "excessive filtering", "excessive nesting", "too many aggregates",
        "too many columns", "too many joins", "excessive string manipulations",
        "overuse of functions", "over engineered"
    ],

    # 3) Hardcoding
    "Hardcoding Issues": [
        "hardcoded column names", "hardcoded dataset name", "hardcoded schema",
        "hardcoded table", "hardcoded date", "hardcoded feature",
        "hardcoded filter condition", "magic numbers", "literal values",
        "hardcoded project key", "hardcoded value"
    ],

    # 4) Inefficiency / optimization
    "Inefficient / Optimization Needed": [
        "suboptimal query", "potential performance issue", "inefficient column renaming",
        "inefficient computation", "inefficient concatenation",
        "inefficient data manipulation", "inefficient processing",
        "inefficient transformation", "inefficient date range filtering",
        "inefficient handling missing values", "inefficient merging",
        "could be optimized", "can be optimized", "optimize code", "slow performance"
    ],

    # 5) Clarity/maintainability (incl. commented-out)
    "Clarity & Maintainability Gaps": [
        "lack of clarity", "missing column aliases", "missing comments",
        "missing documentation", "missing context", "no error handling",
        "lack of error handling", "non descriptive variable names",
        "lack of modularity", "lack of parametrization", "poor readability",
        "commented out code", "commented code block", "dead code", "disabled code"
    ],

    # 6) Redundant/repetitive/boilerplate
    "Redundant / Repetitive Code": [
        "redundant code", "repeated code", "repetitive code", "duplicate code",
        "unnecessary repetition", "boilerplate repeated", "duplicate logic"
    ],
}

NOISSUE_COMPLEX_STRONG = [
    r"^\s*[-*]?\s*no\s+(apparent|known|major|significant)?\s*(complexity|complex)\s+issues?\s*(found|identified|detected|observed|reported)?\b",
    r"^\s*[-*]?\s*no\s+issues?\s+identified\b",
    r"^\s*[-*]?\s*simple\s+(?:query|code)\s+(?:with\s+)?no\s+optimization\s+needed\b",
    r"^\s*[-*]?\s*simplistic\s+(?:code\s+structure|data\s+transformation)\b"
]
NOISSUE_COMPLEX_SECONDARY = [
    r"\bno\s+(complexity|complex)\s+issues?\b",
    r"\bno\s+issues?\s+(?:found|identified|detected|observed|reported)\b",
    r"\bsimple\s+(?:query|code)\b"
]
NOISSUE_COMPLEX_EXCLUSIONS = (
    r"\b(except|but|however|though|nevertheless|yet|still|apart\s+from|except\s+for|"
    r"potential|risk|inefficient|optimi[sz]e|complex|performance|slow|suboptimal)\b"
)
NOISSUE_CONFIG_COMPLEX = {
    "strong": NOISSUE_COMPLEX_STRONG,
    "secondary": NOISSUE_COMPLEX_SECONDARY,
    "exclusions": NOISSUE_COMPLEX_EXCLUSIONS,
}


df_complexity_labeled = assign_issue_names_with_clouds(
    complexity_df,                         # <- your dataframe with DESCRIPTION
    seed_spec=SEED_SPEC_COMPLEX,
    noissue_config=NOISSUE_CONFIG_COMPLEX,
    text_col="DESCRIPTION",
    sim_threshold=0.14,                    # slightly looser for recall
    ngram_range=(1, 3),                    # capture more phrasing variants
    use_char_ngrams=True,                  # typo/short-token robustness
    token_pattern=r"(?u)\b[\w\./+\-*=:%]+\b",
    regex_boosts=REGEX_BOOSTS_COMPLEX,
    boost_weight=0.45,                     # strong nudge toward matches
    force_on_regex=False,                  # set True if you want regex to hard-assign
    make_clouds=False
)

print(df_complexity_labeled["ISSUE_NAME"].value_counts(dropna=False))
