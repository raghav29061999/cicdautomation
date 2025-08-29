REGEX_BOOSTS_SECURITY = {
    # 1) SQL Injection
    "SQL Injections": [
        r"\bsql\s*injection\b",
        r"\b(union\s+select|or\s+1\s*=\s*1|or\s+'1'='1'|--\s*$|;--)\b",
        r"\b(user\s*input|request(?:\.|_)?(?:args|params)|input)\s+(?:in|concatenated\s+into)\s+(?:query|sql)\b",
        r"\b(string\s*concat(?:enation)?|concatenate|build)\s+(?:query|sql)\b",
        r"\bunparameteri[sz]ed\b|\bnot\s+parameteri[sz]ed\b|\bmissing\s+parameter(s)?\b",
        r"\bcursor\.execute\([^)]*(\+|format\(|%[^)]*s)[^)]*\)",   # concatenation/format patterns
        r"\bexec(?:ute)?\s*\(",                                     # generic execute/exec
        r"\bunsanitiz(?:ed|e)\s+input\b|\bno\s+(?:escaping|sanitization)\b"
    ],

    # 2) Hardcoded Credentials
    "Hardcoded Credentials": [
        r"\bhardcoded\s+(?:credential|secret|password|api\s*key)s?\b",
        r"\b(api_?key|access[_-]?key|secret[_-]?key|client[_-]?secret|private\s+key|password|passwd|pwd|token)\b",
        r"\baws\s+(?:access|secret)\s+key\b|\bgcp\b|\bazure\b",
        r"Authorization:\s*Bearer\s+[A-Za-z0-9\-_\.=]{8,}",
        r"-----BEGIN\s+(?:RSA|DSA|EC)\s+PRIVATE\s+KEY-----"
    ],

    # 3) Hardcoded Values
    "Hardcoded Values": [
        r"\bhard[-\s]?cod(?:e|ed)\b",
        r"\bhardcoded\s+(?:url|endpoint|path|ip\s*address|host|port|filename|file\s*path|column|dataset|table|schema|value)s?\b",
        r"\bmagic\s+number[s]?\b|\bliteral\s+value[s]?\b",
        r"\bhttp[s]?://\S+"   # constant URL
    ],

    # 4) Library Issues
    "Library Issues": [
        r"\bCVE-\d{4}-\d+\b",
        r"\b(outdated|vulnerable|deprecated|end[-\s]?of[-\s]?life|EOL)\b",
        r"\bupgrade\s+(?:required|needed|to)\b|\bsecurity\s+advisory\b",
        r"\bdependency|package|requirements\.txt|package\.json\b",
        r"\bssl\s*verify\s*=\s*false\b"
    ],
}
--------------------
REGEX_BOOSTS_FUNCTIONALITY = {
    # 1) Ambiguous / Redundant
    "Ambiguous/Redundant Code": [
        r"\bambig(?:u|)ous\b",
        r"\bambig(?:u|)ous\s+(?:col(?:umn)?|name|ref(?:erence)?)\b",
        r"\bredundan(?:t|cy)\b|\bduplicate\s+code\b|\brepeated\b|\brepetitive\b|\bunused\s+(?:var|variable|import)\b|\bshadow(?:ed|ing)\s+var\b"
    ],

    # 2) Commented-out
    "Commented-Out Code Present": [
        r"\bcommented[-\s]?out\b|\bcommented\s+code\b|\bcommented\s+block\b",
        r"\bdead\s+code\b|\bdisabled\s+code\b|\bcommented.*logic\b|\bTODO\b"
    ],

    # 3) Hardcoded values
    "Hardcoded Values": [
        r"\bhard[-\s]?cod(?:e|ed)\b",
        r"\bhardcoded\s+(?:file|path|url|column|dataset|name|table|schema|value)s?\b",
        r"\bmagic\s+number[s]?\b|\bliteral\s+value[s]?\b|\binline\s+constant\b"
    ],

    # 4) Incomplete / Incorrect / Inconsistent
    "Incomplete/Incorrect/Inconsistent Implementation": [
        r"\bincomplete\b|\bpartial\s+implementation\b|\bnot\s+implemented\b|\bplaceholder\b|\bstub\b",
        r"\black\s+of\s+data\s+filter(?:ing)?\b|\bmissing\s+filter\b",
        r"\bno\s+(?:error|exception)\s+handling\b|\bno\s+(?:data\s+processing|transformation)\b|\bmissing\s+validation\b",
        r"\bincorrect\s+calculat\w*\b|\bcalculat\w*\s+(?:is|are)\s+incorrect\b",
        r"\bincorrect\s+(?:mapping|conversion|cast|logic|handling)\b|\bwrong\s+(?:calc|mapping)\b",
        r"\binconsistent\b|\bmismatch(?:ed)?\s+(?:type|schema)\b|\btype\s+mismatch\b",
        r"\bincorrect\s+assumption\b|\bassumes\b"
    ],

    # 5) Inefficient (implementation)
    "Inefficient Implementation": [
        r"\b(inefficient|inefficent)\b|\bsuboptimal\b|\bnot\s+optimized\b",
        r"\bnon[-\s]?vectori[sz]ed\b|\brow[-\s]?by[-\s]?row\b|\bnested\s+loop\b|\bslow\s+loop\b",
        r"\bo\(?n\^?2\)?\b|\bo\(\s*n\s*\^\s*2\s*\)\b|\brecompute[s]?\s+repeatedly\b"
    ],

    # 6) Inefficient (query-specific)
    "Inefficient Query": [
        r"\binefficient\s+(?:query|subquery)\b|\bslow\s+query\b|\bexpensive\s+query\b",
        r"\bfull\s+table\s+scan\b|\btable\s+scan\b",
        r"\bmissing\s+index\b|\bno\s+index\b",
        r"\bselect\s*\*\b",
        r"\b(cartesian|cross)\s+join\b|\bn\+1\s+query\b",
        r"\bno\s+where\b|\bno\s+filter\b|\bno\s+limit\b",
        r"\bno\s+partition\s+(?:pruning|filter)\b|\bno\s+predicate\s+pushdown\b",
        r"\bbad\s+join\s+order\b|\bskewed\s+join\b|\bexcessive\s+shuffle\b"
    ],

    # 7) Potential risks/issues
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
-------------
REGEX_BOOSTS_COMPLEXITY = {
    # 1) High / Overly complex logic & structure
    "High/Overly Complex Logic & Structure": [
        r"\b(high|overly)\s+complex\b|\bcomplex\s+(?:query|logic|structure)\b",
        r"\bnested\s+(?:calc|calculation|case|if|when|conditional|query|subquer(?:y|ies))\b",
        r"\bdeep\s+nest(?:ing)?\b|\blarge\s+number\s+of\s+condition",
        r"\bjoin\s+condition\b|\bdate\s+(?:calc|calculation|manipulation)\b",
        r"\blambda\s+functions?\b|\bloop[s]?\b|\bconditional\s+logic\b"
    ],

    # 2) Excessive operations / overuse of functions
    "Excessive Operations / Overuse of Functions": [
        r"\bexcessive\b|\btoo\s+many\b|\bover\s*use\b|\boveruse\b|\bover[-\s]?engineer",
        r"\b(excessive|too\s+many)\s+(?:columns|joins|aggregates?|group(?:ing)?|filters?|params?|parameters?)\b",
        r"\b(excessive|too\s+many)\s+(?:string\s+manipulations?|nesting|functions?)\b"
    ],

    # 3) Hardcoding issues
    "Hardcoding Issues": [
        r"\bhard[-\s]?cod(?:e|ed)\b",
        r"\bhardcoded\s+(?:column|dataset|schema|table|date|feature|filter\s+condition|project\s+key|value)s?\b",
        r"\bmagic\s+number[s]?\b|\bliteral\s+value[s]?\b|\babsolute\s+path\b"
    ],

    # 4) Inefficient / optimization needed
    "Inefficient / Optimization Needed": [
        r"\b(inefficient|inefficent)\b|\bsuboptimal\b|\bslow\b|\bexpensive\b",
        r"\b(could|can)\s+be\s+optimized\b|\boptimi[sz]e\b",
        r"\binefficient\s+(?:computation|concatenation|processing|manipulation|transformation|merg(?:e|ing))\b",
        r"\bdate\s+range\s+filtering\b|\bhandling\s+missing\s+values\b"
    ],

    # 5) Clarity & maintainability gaps (incl. commented)
    "Clarity & Maintainability Gaps": [
        r"\black\s+of\s+clarity\b|\bmissing\s+(?:alias|aliases|comments?|documentation|context)\b",
        r"\bno\s+(?:error|exception)\s+handling\b|\black\s+of\s+error\s+handling\b",
        r"\bnon[-\s]?descriptive\s+variable\b|\bpoor\s+readability\b",
        r"\black\s+of\s+(?:modularity|parametrization)\b",
        r"\bcommented[-\s]?out\b|\bcommented\s+code\b|\bdead\s+code\b|\bdisabled\s+code\b"
    ],

    # 6) Redundant / repetitive code
    "Redundant / Repetitive Code": [
        r"\bredundan(?:t|cy)\b|\bduplicate\s+code\b|\brepeated\b|\brepetitive\b|\bboilerplate\b",
        r"\bduplicate\s+logic\b|\bunnecessary\s+repetition\b"
    ],
}
