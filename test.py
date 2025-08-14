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

def _compile_list(patterns):
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


# ---------------------- Main (dynamic + regex boosts) ----------------------
def assign_issue_names_with_clouds(
    df: pd.DataFrame,
    seed_spec: Dict[str, List[str]],
    noissue_config: Dict[str, Union[List[Union[str, re.Pattern]], str, re.Pattern]] = None,
    *,
    text_col: str = "DESCRIPTION",
    sim_threshold: float = 0.15,
    ngram_range=(1, 3),                 # widen to (1,3) for phrasing variants
    min_df: int = 3,
    max_df: float = 0.90,
    use_char_ngrams: bool = True,       # turn on to handle typos like "ambigous"
    token_pattern: str = r"(?u)\b[\w\./+\-*=:%]+\b",  # keep symbols such as + * / = :
    make_clouds: bool = False,
    no_issue_label: str = "No Issues",
    unclustered_label: str = "Unclustered",
    # NEW:
    regex_boosts: Dict[str, List[Union[str, re.Pattern]]] = None,
    boost_weight: float = 0.30,
    force_on_regex: bool = False,
) -> pd.DataFrame:
    """
    Dynamically assigns ISSUE_NAME using seed-guided TF-IDF cosine similarity + optional 'No Issues' regex
    + optional regex-based boosts/overrides per label.

    ISSUE_NAME ∈ {all keys of seed_spec} ∪ {no_issue_label, unclustered_label}
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

    # Seeds
    seed_labels = list(seed_spec.keys()) if seed_spec else []
    if len(seed_labels) == 0:
        assigned = np.where(noissue_mask, no_issue_label, unclustered_label)
        out["ISSUE_NAME"] = assigned
        out.drop(columns=["_clean"], inplace=True)
        return out

    seed_texts = []
    for lbl in seed_labels:
        syns = seed_spec.get(lbl, []) or []
        seed_texts.append((lbl + " | " + " ".join(syns)).strip())

    # Vectorize docs + seeds
    vec_word = TfidfVectorizer(
        ngram_range=ngram_range,
        min_df=min_df,
        max_df=max_df,
        sublinear_tf=True,
        strip_accents="unicode",
        token_pattern=token_pattern
    )
    X_docs = vec_word.fit_transform(out["_clean"].tolist())
    X_seeds = vec_word.transform(seed_texts)

    # Optionally add char n-grams
    if use_char_ngrams:
        from scipy.sparse import hstack
        vec_char = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3,5),
            min_df=min_df,
            max_df=max_df,
            sublinear_tf=True
        )
        Xc_docs = vec_char.fit_transform(out["_clean"].tolist())
        Xc_seeds = vec_char.transform(seed_texts)
        X_docs = hstack([X_docs, Xc_docs], format="csr")
        X_seeds = hstack([X_seeds, Xc_seeds], format="csr")

    # Cosine similarity
    sims = linear_kernel(X_docs, X_seeds)  # (n_docs, n_labels)

    # ---------- Regex boosts / overrides ----------
    if regex_boosts:
        compiled = {lbl: _compile_list(regex_boosts.get(lbl)) for lbl in seed_labels}
        # For each label, create a boolean mask of rows that match any of its regex
        for j, lbl in enumerate(seed_labels):
            pats = compiled.get(lbl) or []
            if not pats:
                continue
            match_mask = out["_clean"].map(lambda s: any(p.search(s) for p in pats))
            if force_on_regex:
                # Hard-assign by setting this label's score very high and others low
                sims[match_mask.values, :] = 0.0
                sims[match_mask.values, j] = 1.0
            else:
                # Soft boost: add a constant to the similarity for that label
                sims[match_mask.values, j] += boost_weight

    # Nearest label + threshold
    best_ix = sims.argmax(axis=1)
    best_sim = sims[np.arange(sims.shape[0]), best_ix]
    best_labels = np.array(seed_labels, dtype=object)[best_ix]

    assigned = np.where(best_sim >= sim_threshold, best_labels, unclustered_label)
    assigned = np.where(noissue_mask, no_issue_label, assigned)

    out["ISSUE_NAME"] = assigned
    out.drop(columns=["_clean"], inplace=True)
    return out
