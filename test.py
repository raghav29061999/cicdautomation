import re
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

# --------------------------------------
# Config: edit/tune synonyms & threshold
# --------------------------------------
TEXT_COL = "DESCRIPTION"
SIM_THRESHOLD = 0.15  # lower to be more permissive, raise to be stricter

SEED_SPEC = {
    "SQL Injections": [
        "sql injection", "unparameterized", "parameter", "concat query",
        "raw query", "cursor execute", "user input in query", "select from +"
    ],
    "Hardcoded Credentials": [
        "hardcoded secret", "hardcoded password", "api key", "apikey",
        "access key", "secret key", "client_secret", "private key", "token in code"
    ],
    "Hardcoded Values": [
        "hardcoded value", "magic number", "hardcoded url", "base url in code",
        "env var literal", "config inline", "constant value"
    ],
    "Library Issues": [
        "outdated dependency", "vulnerable package", "cve", "upgrade required",
        "deprecated library", "unsupported version", "security advisory"
    ],
    # NOTE: "No Issues" & "Unclustered" handled separately
}

# ---------- Improved "No Issues" detection ----------
# Strong starters (anchored at line start)
NOISSUE_STRONG_START = [
    r"^\s*[-*]?\s*no\s+(apparent|known|obvious|significant|major)?\s*(security\s+)?issues?\s*(found|detected|observed|identified|reported|present)?(\s+at\s+this\s+time|\,?\s*currently)?\b",
    r"^\s*[-*]?\s*no\s+vulnerabilit(?:y|ies)\s*(found|detected|observed|identified|reported)?\b",
    r"^\s*[-*]?\s*no\s+issues?\b",
]

# Secondary anywhere checks (only if no exclusions)
NOISSUE_SECONDARY = [
    r"\bno\s+(security\s+)?issues?\s*(found|detected|observed|identified|reported)?\b",
    r"\bno\s+vulnerabilit(?:y|ies)\s*(found|detected|observed|identified|reported)?\b",
    r"\bno\s+findings?\b",
]

# Exclusions to avoid false positives like "no issues, however ..."
NOISSUE_EXCLUSIONS = r"\b(except|but|however|though|nevertheless|yet|still|apart\s+from|except\s+for)\b"

COMPILED_NOISSUE_STRONG = [re.compile(p, re.I) for p in NOISSUE_STRONG_START]
COMPILED_NOISSUE_SECONDARY = [re.compile(p, re.I) for p in NOISSUE_SECONDARY]
COMPILED_NOISSUE_EXC = re.compile(NOISSUE_EXCLUSIONS, re.I)

def _clean_text(t: str) -> str:
    if not isinstance(t, str):
        return ""
    s = t.lower()
    s = re.sub(r"https?://\S+", " url ", s)
    s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", " email ", s)
    s = re.sub(r"[A-Fa-f0-9]{32,}", " hex ", s)  # long hashes/uuids/keys
    s = re.sub(r"\s+", " ", s).strip()
    return s

def is_no_issue_text(s: str) -> bool:
    """High-precision detector for 'No Issues' style statements."""
    if not s:
        return False
    # 1) Strong 'start of line' phrasing → accept immediately
    if any(p.search(s) for p in COMPILED_NOISSUE_STRONG):
        return True
    # 2) Secondary phrasing → accept only if no exclusions
    if any(p.search(s) for p in COMPILED_NOISSUE_SECONDARY):
        if not COMPILED_NOISSUE_EXC.search(s):
            return True
    return False

def add_issue_name_column(
    security_df: pd.DataFrame,
    seed_spec: dict = SEED_SPEC,
    text_col: str = TEXT_COL,
    sim_threshold: float = SIM_THRESHOLD,
) -> pd.DataFrame:
    """
    Adds ISSUE_NAME to security_df with ONLY these values:
      {SQL Injections, Hardcoded Credentials, Hardcoded Values, Library Issues, No Issues, Unclustered}
    """
    df = security_df.copy()
    if text_col not in df.columns:
        raise KeyError(f"Column '{text_col}' not found")

    # Clean text + "No Issues" detection
    df[text_col] = df[text_col].fillna("").astype(str)
    df["_clean"] = df[text_col].map(_clean_text)
    no_issue_mask = df["_clean"].map(is_no_issue_text)

    # Build shared TF-IDF for docs + seeds (4 issue seeds)
    seed_labels = list(seed_spec.keys())  # 4 labels
    seed_texts = [" ".join(seed_spec[label]) if seed_spec[label] else label for label in seed_labels]

    vec = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=3,
        max_df=0.90,
        sublinear_tf=True,
        strip_accents="unicode",
    )
    X_docs = vec.fit_transform(df["_clean"].tolist())
    X_seeds = vec.transform(seed_texts)

    sims = linear_kernel(X_docs, X_seeds)  # (n_docs, 4)
    best_ix = sims.argmax(axis=1)
    best_sim = sims[np.arange(sims.shape[0]), best_ix]
    best_labels = np.array(seed_labels, dtype=object)[best_ix]

    assigned = np.where(best_sim >= sim_threshold, best_labels, "Unclustered")
    assigned = np.where(no_issue_mask, "No Issues", assigned)

    df["ISSUE_NAME"] = assigned
    df.drop(columns=["_clean"], inplace=True)
    return df
