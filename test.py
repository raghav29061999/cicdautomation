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

# Provide synonyms for the 4 issue-type seeds used in similarity
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
    # NOTE: "No Issues" & "Unclustered" are not used for similarity — handled below
}

NO_ISSUE_PATTERNS = [
    r"\bno\s+(security\s+)?issues?\s+found\b",
    r"\bno\s+(issue|issues)\b",
    r"\bno\s+vulnerabilit(y|ies)\b",
]
COMPILED_NOISSUE = [re.compile(p, re.I) for p in NO_ISSUE_PATTERNS]

def _clean_text(t: str) -> str:
    if not isinstance(t, str):
        return ""
    s = t.lower()
    s = re.sub(r"https?://\S+", " url ", s)
    s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", " email ", s)
    s = re.sub(r"[A-Fa-f0-9]{32,}", " hex ", s)  # long hashes/uuids/keys
    s = re.sub(r"\s+", " ", s).strip()
    return s

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

    # Clean text
    df[text_col] = df[text_col].fillna("").astype(str)
    df["_clean"] = df[text_col].map(_clean_text)

    # Detect explicit "No Issues" first (overrides everything)
    no_issue_mask = df["_clean"].map(lambda s: any(p.search(s) for p in COMPILED_NOISSUE))

    # Build TF-IDF space shared by docs + seed strings
    seed_labels = list(seed_spec.keys())  # 4 labels used in similarity
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

    # Cosine similarity (dot product in L2-normalized TFIDF space)
    sims = linear_kernel(X_docs, X_seeds)  # shape: (n_docs, 4)
    best_ix = sims.argmax(axis=1)
    best_sim = sims[np.arange(sims.shape[0]), best_ix]
    best_labels = np.array(seed_labels, dtype=object)[best_ix]

    # Assign from seeds with threshold; otherwise Unclustered
    assigned = np.where(best_sim >= sim_threshold, best_labels, "Unclustered")

    # Override with "No Issues"
    assigned = np.where(no_issue_mask, "No Issues", assigned)

    # Final: exactly the six-class column
    df["ISSUE_NAME"] = assigned

    # Optional sanity check (can comment out in prod)
    # allowed = set(seed_labels) | {"No Issues", "Unclustered"}
    # assert set(df["ISSUE_NAME"].unique()).issubset(allowed)

    # Clean up helper column
    df.drop(columns=["_clean"], inplace=True)
    return df

# -------------------------
# Example usage:
# -------------------------
# df_with_issue = add_issue_name_column(security_df)
# print(df_with_issue["ISSUE_NAME"].value_counts(dropna=False))
# # Expect only up to 6 categories (your 4 seeds + "No Issues" + "Unclustered")
