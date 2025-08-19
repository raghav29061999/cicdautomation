REGEX_BOOSTS_FUNC = {
    # Ambiguous/Redundant
    "Ambiguous/Redundant Code": [
        r"\bambig(?:u|)ous\b",                      # handles 'ambigous' typo too
        r"\bambig(?:u|)ous\s+(?:col|column|name|ref)",
        r"\bredundant\b|\bduplicate\s+code\b"
    ],
    # Commented out
    "Commented-Out Code Present": [
        r"\bcommented[-\s]?out\b",
        r"\bcommented\s+code\b|\bdead\s+code\b|\bdisabled\s+code\b"
    ],
    # Hardcoded values
    "Hardcoded Values": [
        r"\bhardcod(?:e|ed)\b",
        r"\bmagic\s+number\b|\bliteral\s+value\b|\bconstant\s+value\b",
        r"\bhardcoded\s+(?:column|dataset|file\s*path|url|name)s?\b"
    ],
    # Incomplete/Incorrect/Inconsistent
    "Incomplete/Incorrect/Inconsistent Implementation": [
        r"\bincomplete\b|\black\s+of\s+data\s+filter(?:ing)?\b|\bno\s+error\s+handling\b",
        r"\bno\s+(?:data\s+processing|transformation)\b",
        r"\bincorrect\s+calculat\w*\b|\bcalculat\w*\s+(?:is|are)\s+incorrect\b",
        r"\bincorrect\s+(?:column\s+)?(map|mapping|conversion|logic|handling)\b",
        r"\binconsis(?:ten|t) \w*|\binconsistent\b"
    ],
    # Inefficient (implementation)
    "Inefficient Implementation": [
        r"^\s*inefficient\b",                       # starts with 'inefficient ...'
        r"\binefficient\s+(?:computation|processing|retrieval|sorting|archiving|deduplication)\b",
        r"\bnot\s+optimized\b|\bsuboptimal\b|\bmultiple\s+complex\s+conditions\b"
    ],
    # Inefficient Query (query-specific)
    "Inefficient Query": [
        r"\binefficient\s+(?:query|subquery)\b",
        r"\bselect\s*\*\b|\bcartesian\s+join\b|\bfull\s+table\s+scan\b|\bmissing\s+index\b",
        r"\bn\+1\s+query\b"
    ],
    # Potential risks/issues
    "Potential Risks/Issues": [
        r"^\s*potential\b",
        r"\bmay\s+return\s+large\s+dataset\b|\bmight\s+result\b|\bcould\s+lead\b",
        r"\bpotential\s+(?:data\s+loss|null\s+values|performance|rounding)\b"
    ],
}
