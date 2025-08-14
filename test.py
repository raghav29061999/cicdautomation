import re
import numpy as np
import pandas as pd
from typing import Dict, List, Union

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

# Optional word cloud (QA only)
import matplotlib.pyplot as plt
try:
    from wordcloud import WordCloud
    _WORDCLOUD = True
except Exception:
    _WORDCLOUD = False


# ---------------------- Utilities ----------------------
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
    for p in (patterns or []):
        out.append(p if isinstance(p, re.Pattern) else re.compile(p, re.I))
    return out

def _is_no_issue_text(s: str,
                      compiled_strong: List[re.Pattern],
                      compiled_secondary: List[re.Pattern],
                      compiled_exclusions: Union[re.Pattern, None]) -> bool:
    if not s:
        return False
    if compiled_strong and any(p.search(s) for p in compiled_strong):
        return True
    if compiled_secondary and any(p.search(s) for p in compiled_secondary):
        if not (compiled_exclusions and compiled_exclusions.search(s)):
            return True
    return False

def _cloud(texts: List[str], title: str, max_words: int = 150):
    if not texts:
        return
    if _WORDCLOUD:
        wc = WordCloud(width=1100, height=650, background_color="white",
                       collocations=False, max_words=max_words)
        img = wc.generate(" ".join(texts))
        plt.figure(figsize=(10,6)); plt.imshow(img); plt.axis("off"); plt.title(title); plt.show()
    else:
        # Fallback: TF-IDF bar chart
        vec = TfidfVectorizer(ngram_range=(1,2), min_df=3, max_df=0.9,
                              sublinear_tf=True, strip_accents="unicode")
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


# ---------------------- Main (dynamic) ----------------------
def assign_issue_names_with_clouds(
    df: pd.DataFrame,
    seed_spec: Dict[str, List[str]],
    noissue_config: Dict[str, Union[List[Union[str, re.Pattern]], str, re.Pattern]] = None,
    *,
    text_col: str = "DESCRIPTION",
    sim_threshold: float = 0.15,
    ngram_range=(1, 2),
    min_df: int = 3,
    max_df: float = 0.90,
    use_char_ngrams: bool = False,
    make_clouds: bool = False,
    no_issue_label: str = "No Issues",
    unclustered_label: str = "Unclustered",
) -> pd.DataFrame:
    """
    Dynamically assigns ISSUE_NAME using seed-guided TF-IDF cosine similarity + optional 'No Issues' regex.

    ISSUE_NAME ∈ {all keys of seed_spec} ∪ {no_issue_label, unclustered_label}

    Args:
        df: input dataframe
        seed_spec: {label -> [synonyms/phrases, ...]} (any number of labels)
        noissue_config: {
            "strong": [regex or compiled],
            "secondary": [regex or compiled],
            "exclusions": regex or compiled
        } or None (to disable)
        text_col: text column name
        sim_threshold: cosine threshold to accept nearest seed; else unclustered_label
        ngram_range/min_df/max_df/use_char_ngrams: TF-IDF settings
        make_clouds: render overall & per-class word clouds for QA
        no_issue_label / unclustered_label: customize output labels
    Returns:
        Original df + ISSUE_NAME column
    """
    if text_col not in df.columns:
        raise KeyError(f"Column '{text_col}' not found in dataframe")

    # Prepare No-Issue regex (optional)
    strong = secondary = compiled_exc = None
    if noissue_config:
        strong = _compile_list(noissue_config.get("strong"))
        secondary = _compile_list(noissue_config.get("secondary"))
        exc = noissue_config.get("exclusions")
        compiled_exc = exc if isinstance(exc, re.Pattern) else (re.compile(exc, re.I) if exc else None)

    # Clean + detect No Issues
    out = df.copy()
    out[text_col] = out[text_col].fillna("").astype(str)
    out["_clean"] = out[text_col].map(_clean_text)
    if noissue_config:
        noissue_mask = out["_clean"].map(lambda s: _is_no_issue_text(s, strong, secondary, compiled_exc))
    else:
        noissue_mask = pd.Series(False, index=out.index)

    if make_clouds:
        _cloud(out["_clean"].tolist(), "Overall corpus")

    # If no seeds provided, everything is either No Issues or Unclustered
    seed_labels = list(seed_spec.keys()) if seed_spec else []
    if len(seed_labels) == 0:
        assigned = np.where(noissue_mask, no_issue_label, unclustered_label)
        out["ISSUE_NAME"] = assigned
        out.drop(columns=["_clean"], inplace=True)
        if make_clouds:
            for label in [no_issue_label, unclustered_label]:
                subset = out.loc[out["ISSUE_NAME"].eq(label), text_col].tolist()
                if subset:
                    _cloud(subset, f"{label} ({len(subset)})")
        return out

    # Build seed strings ("Label | synonyms") for shared TF-IDF space
    seed_texts = []
    for lbl in seed_labels:
        syns = seed_spec.get(lbl, []) or []
        # allow users to pass either list of phrases or already 'label | terms' style
        seed_texts.append((lbl + " | " + " ".join(syns)).strip())

    # Vectorize docs + seeds
    vec_word = TfidfVectorizer(ngram_range=ngram_range, min_df=min_df, max_df=max_df,
                               sublinear_tf=True, strip_accents="unicode")
    X_docs = vec_word.fit_transform(out["_clean"].tolist())
    X_seeds = vec_word.transform(seed_texts)

    # Optionally add char n-grams (helpful for code-like short strings)
    if use_char_ngrams:
        from scipy.sparse import hstack
        vec_char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3,5),
                                   min_df=min_df, max_df=max_df, sublinear_tf=True)
        Xc_docs = vec_char.fit_transform(out["_clean"].tolist())
        Xc_seeds = vec_char.transform(seed_texts)
        X_docs = hstack([X_docs, Xc_docs], format="csr")
        X_seeds = hstack([X_seeds, Xc_seeds], format="csr")

    # Cosine similarity → nearest seed (or unclustered_label)
    sims = linear_kernel(X_docs, X_seeds)  # (n_docs, n_seeds)
    best_ix = sims.argmax(axis=1)
    best_sim = sims[np.arange(sims.shape[0]), best_ix]
    best_labels = np.array(seed_labels, dtype=object)[best_ix]

    assigned = np.where(best_sim >= sim_threshold, best_labels, unclustered_label)
    assigned = np.where(noissue_mask, no_issue_label, assigned)

    out["ISSUE_NAME"] = assigned
    out.drop(columns=["_clean"], inplace=True)

    if make_clouds:
        for label in seed_labels + [no_issue_label, unclustered_label]:
            subset = out.loc[out["ISSUE_NAME"].eq(label), text_col].tolist()
            if subset:
                _cloud(subset, f"{label} ({len(subset)})")

    return out
