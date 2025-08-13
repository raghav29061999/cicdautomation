import re
import numpy as np
import pandas as pd
from typing import Dict, List, Union

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

# Optional word cloud (falls back to bar chart if not installed)
import matplotlib.pyplot as plt
try:
    from wordcloud import WordCloud
    _WORDCLOUD = True
except Exception:
    _WORDCLOUD = False

# --------------------------------------
# Utilities
# --------------------------------------
def _clean_text(t: str) -> str:
    if not isinstance(t, str):
        return ""
    s = t.lower()
    s = re.sub(r"https?://\S+", " url ", s)
    s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", " email ", s)
    s = re.sub(r"[A-Fa-f0-9]{32,}", " hex ", s)  # long hashes/uuids/keys
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _compile_list(patterns: List[Union[str, re.Pattern]]) -> List[re.Pattern]:
    out = []
    for p in patterns:
        if isinstance(p, re.Pattern):
            out.append(p)
        else:
            out.append(re.compile(p, re.I))
    return out

def _is_no_issue_text(s: str,
                      compiled_strong: List[re.Pattern],
                      compiled_secondary: List[re.Pattern],
                      compiled_exclusions: re.Pattern) -> bool:
    if not s:
        return False
    if any(p.search(s) for p in compiled_strong):
        return True
    if any(p.search(s) for p in compiled_secondary):
        if not compiled_exclusions.search(s):
            return True
    return False

def _cloud(texts: List[str], title: str, max_words: int = 150):
    if not texts:
        return
    if _WORDCLOUD:
        wc = WordCloud(width=1100, height=650, background_color="white", collocations=False, max_words=max_words)
        img = wc.generate(" ".join(texts))
        plt.figure(figsize=(10,6)); plt.imshow(img); plt.axis("off"); plt.title(title); plt.show()
    else:
        # Fallback: show top TF-IDF terms as bars
        vec = TfidfVectorizer(ngram_range=(1,2), min_df=3, max_df=0.9, sublinear_tf=True, strip_accents="unicode")
        X = vec.fit_transform(texts)
        means = np.asarray(X.mean(axis=0)).ravel()
        terms = vec.get_feature_names_out()
        idx = np.argsort(-means)[:30]
        plt.figure(figsize=(10,6))
        plt.barh(range(len(idx)), means[idx][::-1])
        plt.yticks(range(len(idx)), terms[idx][::-1])
        plt.title(f"Top terms — {title}")
        plt.gca().invert_yaxis()
        plt.show()

# --------------------------------------
# Main: add ISSUE_NAME column
# --------------------------------------
def assign_issue_names_with_clouds(
    df: pd.DataFrame,
    seed_spec: Dict[str, List[str]],
    noissue_config: Dict[str, Union[List[Union[str, re.Pattern]], str, re.Pattern]],
    *,
    text_col: str = "DESCRIPTION",
    sim_threshold: float = 0.15,
    ngram_range=(1, 2),
    min_df: int = 3,
    max_df: float = 0.90,
    use_char_ngrams: bool = False,
    make_clouds: bool = False
) -> pd.DataFrame:
    """
    Adds ISSUE_NAME ∈ {SQL Injections, Hardcoded Credentials, Hardcoded Values, Library Issues, No Issues, Unclustered}
    Args:
        df: your dataframe
        seed_spec: dict with exactly 4 keys (issue seeds) → list of synonyms
        noissue_config: {
            "strong": [regex strings or compiled],
            "secondary": [regex strings or compiled],
            "exclusions": regex string or compiled
        }
        text_col: column containing text (default "DESCRIPTION")
        sim_threshold: cosine threshold for assigning to a seed; else Unclustered
        ngram_range, min_df, max_df: TF-IDF knobs
        use_char_ngrams: add char_wb 3–5 ngrams (helps with code-ish text)
        make_clouds: show overall + per-class word clouds (for QA/tuning)
    Returns:
        df_out: original df + ISSUE_NAME column
    """
    if text_col not in df.columns:
        raise KeyError(f"Column '{text_col}' not in dataframe")

    # Validate seeds (we expect exactly the 4 issue buckets here)
    expected_4 = {"SQL Injections", "Hardcoded Credentials", "Hardcoded Values", "Library Issues"}
    if set(seed_spec.keys()) != expected_4:
        raise ValueError(f"seed_spec must have exactly these keys: {expected_4}")

    # Compile no-issue regex config
    strong = _compile_list(noissue_config.get("strong", []))
    secondary = _compile_list(noissue_config.get("secondary", []))
    exc = noissue_config.get("exclusions", r"")
    compiled_exc = exc if isinstance(exc, re.Pattern) else re.compile(exc or r"$^", re.I)

    # Clean and detect "No Issues"
    out = df.copy()
    out[text_col] = out[text_col].fillna("").astype(str)
    out["_clean"] = out[text_col].map(_clean_text)
    noissue_mask = out["_clean"].map(lambda s: _is_no_issue_text(s, strong, secondary, compiled_exc))

    # Optional: overall cloud
    if make_clouds:
        _cloud(out["_clean"].tolist(), "Overall corpus")

    # Build seed strings ("Label | synonyms ...") for TF-IDF space
    seed_labels = list(expected_4)  # fixed order not required
    seed_texts = []
    for lbl in seed_labels:
        syns = seed_spec.get(lbl, [])
        seed_texts.append((lbl + " | " + " ".join(syns)).strip())

    # Vectorize docs + seeds in shared space
    vec_word = TfidfVectorizer(ngram_range=ngram_range, min_df=min_df, max_df=max_df,
                               sublinear_tf=True, strip_accents="unicode")
    X_docs = vec_word.fit_transform(out["_clean"].tolist())
    X_seeds = vec_word.transform(seed_texts)

    # Optionally append char ngrams
    feature_names = list(vec_word.get_feature_names_out())
    if use_char_ngrams:
        from scipy.sparse import hstack
        vec_char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3,5), min_df=min_df, max_df=max_df,
                                   sublinear_tf=True)
        Xc_docs = vec_char.fit_transform(out["_clean"].tolist())
        Xc_seeds = vec_char.transform(seed_texts)
        X_docs = hstack([X_docs, Xc_docs], format="csr")
        X_seeds = hstack([X_seeds, Xc_seeds], format="csr")
        feature_names += list(vec_char.get_feature_names_out())

    # Seed assignment via cosine similarity
    sims = linear_kernel(X_docs, X_seeds)                # (n_docs, 4)
    best_ix = sims.argmax(axis=1)                        # best seed index per row
    best_sim = sims[np.arange(sims.shape[0]), best_ix]   # best similarity per row
    best_labels = np.array(seed_labels, dtype=object)[best_ix]

    assigned = np.where(best_sim >= sim_threshold, best_labels, "Unclustered")
    assigned = np.where(noissue_mask, "No Issues", assigned)

    out["ISSUE_NAME"] = assigned
    out.drop(columns=["_clean"], inplace=True)

    # Optional: per-class word clouds (post-assign)
    if make_clouds:
        for label in ["SQL Injections","Hardcoded Credentials","Hardcoded Values","Library Issues","No Issues","Unclustered"]:
            subset = out.loc[out["ISSUE_NAME"].eq(label), text_col].tolist()
            if subset:
                _cloud(subset, f"{label} ({len(subset)})")

    return out
////////////
# Your seeds (4 top issue types)
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
}

# Your improved No-Issue regex config
NOISSUE_STRONG_START = [
    r"^\s*[-*]?\s*no\s+(apparent|known|obvious|significant|major)?\s*(security\s+)?issues?\s*(found|detected|observed|identified|reported|present)?(\s+at\s+this\s+time|\,?\s*currently)?\b",
    r"^\s*[-*]?\s*no\s+vulnerabilit(?:y|ies)\s*(found|detected|observed|identified|reported)?\b",
    r"^\s*[-*]?\s*no\s+issues?\b",
]
NOISSUE_SECONDARY = [
    r"\bno\s+(security\s+)?issues?\s*(found|detected|observed|identified|reported)?\b",
    r"\bno\s+vulnerabilit(?:y|ies)\s*(found|detected|observed|identified|reported)?\b",
    r"\bno\s+findings?\b",
]
NOISSUE_EXCLUSIONS = r"\b(except|but|however|though|nevertheless|yet|still|apart\s+from|except\s+for)\b"

NOISSUE_CONFIG = {
    "strong": NOISSUE_STRONG_START,
    "secondary": NOISSUE_SECONDARY,
    "exclusions": NOISSUE_EXCLUSIONS,
}

# Run (adds ISSUE_NAME)
df_with_issue = assign_issue_names_with_clouds(
    security_df,
    SEED_SPEC,
    NOISSUE_CONFIG,
    text_col="DESCRIPTION",
    sim_threshold=0.15,       # lower to reduce Unclustered
    ngram_range=(1, 2),       # (1,3) if you want broader matching
    use_char_ngrams=False,    # True helps with short/code-like strings
    make_clouds=False         # True to render clouds for QA
)

# Sanity check: exactly the six values
print(df_with_issue["ISSUE_NAME"].value_counts(dropna=False))
# Save for dashboard
# df_with_issue.to_parquet("security_issue_names.parquet", index=False)
