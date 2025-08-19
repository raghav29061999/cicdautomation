NOISSUE_FUNC_STRONG = [
    r"^\s*[-*]?\s*no\s+(apparent|known|major|significant)?\s*(functionality|functional)\s+issues?\s*(found|identified|detected|observed|reported)?\b",
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
