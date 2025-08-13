import re
import numpy as np
import pandas as pd

from collections import defaultdict, Counter

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from sklearn.decomposition import TruncatedSVD
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score

import matplotlib.pyplot as plt

# Optional word cloud support (falls back to a bar chart if not installed)
try:
    from wordcloud import WordCloud
    WORDCLOUD_AVAILABLE = True
except Exception:
    WORDCLOUD_AVAILABLE = False

# -----------------------------
# Configuration
# -----------------------------
TEXT_COL = "DESCRIPTION"
RANDOM_STATE = 42

# Vectorization
WORD_MIN_DF = 3
WORD_MAX_DF = 0.90
NGRAM_RANGE = (1, 2)
USE_CHAR_NGRAMS = False  # flip to True if texts are very short/noisy

# SVD for clustering stability/speed
USE_SVD = True
SVD_COMPONENTS = 120

# Seed assignment
SIM_THRESHOLD = 0.15   # if max similarity to any seed < threshold -> Unassigned

# Clustering per seed bucket
SUBK_K_RANGE = range(2, 7)   # try 2..6 clusters per bucket; auto-pick with silhouette
SUBK_MIN_SIZE = 100          # small buckets skip clustering (treated as 1 group)

# Detect "No issues"
NO_ISSUE_PATTERNS = [
    r"\bno\s+(security\s+)?issues?\s+found\b",
    r"\bno\s+(issue|issues)\b",
    r"\bno\s+vulnerabilit(y|ies)\b",
]

COMPILED_NOISSUE = [re.compile(p, re.I) for p in NO_ISSUE_PATTERNS]

def is_no_issue(s: str) -> bool:
    return any(p.search(s or "") for p in COMPILED_NOISSUE)

# -----------------------------
# Preprocessing
# -----------------------------
def clean_text(t: str) -> str:
    if not isinstance(t, str):
        return ""
    s = t.lower()
    s = re.sub(r"https?://\S+", " url ", s)
    s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", " email ", s)
    s = re.sub(r"[A-Fa-f0-9]{32,}", " hex ", s)  # long hashes/keys/uuids
    s = re.sub(r"\s+", " ", s).strip()
    return s

# -----------------------------
# Word cloud helpers (optional)
# -----------------------------
def plot_wordcloud(texts, title="Word Cloud", max_words=150):
    tokens = " ".join(texts)
    if WORDCLOUD_AVAILABLE:
        wc = WordCloud(width=1000, height=600, background_color="white",
                       max_words=max_words, collocations=False)
        img = wc.generate(tokens)
        plt.figure(figsize=(10, 6))
        plt.imshow(img)
        plt.axis("off")
        plt.title(title)
        plt.show()
    else:
        # Fallback: bar chart of top terms
        vec = TfidfVectorizer(ngram_range=(1,2), min_df=WORD_MIN_DF, max_df=WORD_MAX_DF)
        X = vec.fit_transform(texts)
        mean_tfidf = np.asarray(X.mean(axis=0)).ravel()
        terms = np.array(vec.get_feature_names_out())
        idx = np.argsort(-mean_tfidf)[:30]
        plt.figure(figsize=(10,6))
        plt.barh(range(len(idx)), mean_tfidf[idx][::-1])
        plt.yticks(range(len(idx)), terms[idx][::-1])
        plt.title(f"Top terms (fallback) — {title}")
        plt.gca().invert_yaxis()
        plt.show()

def top_terms_for_mask(X_tfidf, feature_names, mask, topn=8):
    if mask.sum() == 0:
        return []
    mean_vec = np.asarray(X_tfidf[mask].mean(axis=0)).ravel()
    idx = np.argsort(-mean_vec)[:topn]
    return [feature_names[i] for i in idx]

# -----------------------------
# Core pipeline
# -----------------------------
def wordcloud_guided_clustering(
    security_df: pd.DataFrame,
    seeds: list,  # list of cluster names you supply from word-cloud intuition
    text_col: str = TEXT_COL,
    make_plots: bool = False,
):
    """
    1) Clean + 'No issues' detection
    2) TF-IDF for docs + seeds
    3) Assign each doc to nearest seed (cosine), else Unassigned
    4) For each seed bucket, MiniBatchKMeans into subclusters (auto K)
    5) Label subclusters by top terms
    6) (Optional) Word clouds overall / by seed / by subcluster
    """
    df = security_df.copy()
    if text_col not in df.columns:
        raise KeyError(f"Column '{text_col}' not found")

    df[text_col] = df[text_col].fillna("").astype(str)
    df["_clean"] = df[text_col].map(clean_text)
    df["no_issue_seed"] = df["_clean"].map(is_no_issue)

    # 1) Overall word cloud (optional)
    if make_plots:
        plot_wordcloud(df["_clean"].tolist(), "Overall corpus")

    # 2) Build TF-IDF over documents + seed phrases for a shared space
    corpus = df["_clean"].tolist() + [clean_text(s) for s in seeds]
    word_vec = TfidfVectorizer(
        ngram_range=NGRAM_RANGE, min_df=WORD_MIN_DF, max_df=WORD_MAX_DF,
        sublinear_tf=True, strip_accents="unicode"
    )
    X_docs = word_vec.fit_transform(df["_clean"].tolist())
    X_seeds = word_vec.transform([clean_text(s) for s in seeds])
    feature_names = word_vec.get_feature_names_out()

    # Optional char n-grams to help code-y texts
    if USE_CHAR_NGRAMS:
        char_vec = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3,5), min_df=WORD_MIN_DF, max_df=WORD_MAX_DF,
            sublinear_tf=True
        )
        Xc_docs = char_vec.fit_transform(df["_clean"].tolist())
        Xc_seeds = char_vec.transform([clean_text(s) for s in seeds])
        from scipy.sparse import hstack
        X_docs = hstack([X_docs, Xc_docs], format="csr")
        X_seeds = hstack([X_seeds, Xc_seeds], format="csr")
        feature_names = np.concatenate([feature_names, char_vec.get_feature_names_out()])

    # 3) Seed assignment via cosine similarity
    # (TfidfVectorizer L2-normalizes rows, so dot product == cosine similarity)
    sims = linear_kernel(X_docs, X_seeds)  # shape (n_docs, n_seeds)
    seed_ix = sims.argmax(axis=1)
    seed_sim = sims[np.arange(sims.shape[0]), seed_ix]
    seed_names = np.array(seeds, dtype=object)

    assigned_seed = np.where(seed_sim >= SIM_THRESHOLD, seed_names[seed_ix], "Unassigned")
    assigned_seed = np.where(df["no_issue_seed"], "No issues", assigned_seed)
    df["security_seed"] = assigned_seed
    df["security_ml_noissue_proba"] = np.where(df["security_seed"].eq("No issues"), 0.99, 0.01).astype(float)

    # 4) Clustering within each seed bucket (skip No issues / Unassigned / too small)
    cluster_id_counter = 0
    cluster_rows = []  # (cluster_id, seed, label, top_terms, purity, size)

    # Precompute reduced space for faster silhouette if enabled
    if USE_SVD:
        svd = TruncatedSVD(n_components=SVD_COMPONENTS, random_state=RANDOM_STATE)
        X_docs_reduced = svd.fit_transform(X_docs)
    else:
        X_docs_reduced = None

    df["security_cluster_id"] = pd.Series([-1]*len(df), dtype="Int64")
    df["security_cluster_label"] = "No issues"
    df.loc[df["security_seed"].eq("Unassigned"), "security_cluster_label"] = "Unassigned"

    # Helper to label a mask as one single group (no subclusters)
    def label_single_group(mask, seed_name, cluster_id):
        top_terms = top_terms_for_mask(X_docs, feature_names, mask)
        label = f"{seed_name} — " + "/".join(top_terms[:3]) if seed_name not in ("No issues", "Unassigned") else seed_name
        df.loc[mask, "security_cluster_id"] = cluster_id
        df.loc[mask, "security_cluster_label"] = label
        cluster_rows.append((cluster_id, seed_name, label, ", ".join(top_terms), 1.0, int(mask.sum())))

    for seed in list(seed_names) + ["Unassigned"]:
        if seed in ("No issues",):  # skip no-issue
            continue
        mask_seed = df["security_seed"].eq(seed)
        size = int(mask_seed.sum())
        if size == 0:
            continue
        if size < SUBK_MIN_SIZE:
            label_single_group(mask_seed, seed, cluster_id_counter)
            cluster_id_counter += 1
            if make_plots:
                plot_wordcloud(df.loc[mask_seed, "_clean"].tolist(), f"{seed} (size={size})")
            continue

        # Prepare features for this bucket
        X_bucket = X_docs[mask_seed]
        if USE_SVD:
            Xr_bucket = X_docs_reduced[mask_seed.values]
        else:
            Xr_bucket = X_bucket

        # Auto-pick K with silhouette over SUBK_K_RANGE
        best_k, best_model, best_score = None, None, -1
        for k in SUBK_K_RANGE:
            if k >= size:  # safety
                continue
            model = MiniBatchKMeans(n_clusters=k, random_state=RANDOM_STATE, n_init="auto", batch_size=2048)
            labels = model.fit_predict(Xr_bucket)
            if len(set(labels)) < 2:
                continue
            try:
                score = silhouette_score(Xr_bucket, labels, metric="euclidean")
            except Exception:
                score = -1
            if score > best_score:
                best_k, best_model, best_score = k, model, score

        if best_model is None:
            # Fallback: single group
            label_single_group(mask_seed, seed, cluster_id_counter)
            cluster_id_counter += 1
            if make_plots:
                plot_wordcloud(df.loc[mask_seed, "_clean"].tolist(), f"{seed} (single)")
            continue

        # Apply best model and label subclusters
        labels = best_model.predict(Xr_bucket)
        mask_idx = np.where(mask_seed)[0]
        for subk in range(best_model.n_clusters):
            sub_mask_local = (labels == subk)
            if sub_mask_local.sum() == 0:
                continue
            doc_idx = mask_idx[sub_mask_local]
            global_mask = df.index.isin(doc_idx)

            # Top terms for this subcluster
            top_terms = top_terms_for_mask(X_docs, feature_names, global_mask)
            cluster_id = cluster_id_counter
            cluster_id_counter += 1

            label = f"{seed} — " + "/".join(top_terms[:3]) if seed not in ("Unassigned",) else "Unassigned"
            df.loc[global_mask, "security_cluster_id"] = cluster_id
            df.loc[global_mask, "security_cluster_label"] = label

            cluster_rows.append(
                (cluster_id, seed, label, ", ".join(top_terms), np.nan, int(global_mask.sum()))
            )

            if make_plots:
                plot_wordcloud(df.loc[global_mask, "_clean"].tolist(), f"{label} (n={int(global_mask.sum())})")

    # Wrap up remaining 'No issues'
    mask_no = df["security_seed"].eq("No issues")
    if mask_no.any():
        df.loc[mask_no, "security_cluster_id"] = pd.Series([-1]*mask_no.sum(), dtype="Int64")
        df.loc[mask_no, "security_cluster_label"] = "No issues"

    # Final primary label
    df["security_ml_primary"] = df["security_cluster_label"]
    df.drop(columns=["_clean"], inplace=True)

    # Summary for dashboard
    summary = (
        df["security_ml_primary"]
        .value_counts(dropna=False)
        .rename_axis("label")
        .reset_index(name="count")
    )
    summary["share_%"] = (summary["count"] * 100.0 / len(df)).round(2)

    # Optional: return cluster metadata as DataFrame
    cluster_meta = pd.DataFrame(
        cluster_rows, columns=["security_cluster_id","seed","label","top_terms","purity","size"]
    ).sort_values("size", ascending=False)

    return df, summary, cluster_meta

# -----------------------------
# Example usage
# -----------------------------
# 1) Provide your top-level seeds (from your word clouds)
seeds = [
    "SQL Injection vulnerability",
    "Hardcoded secret / API key",
    "PII exposure in logs",
    "Weak crypto / hashing",
    "Command injection / shell",
    "Path traversal",
    "Auth/JWT/CORS/SSL misconfig"
]

# 2) Run the pipeline (set make_plots=True to see clouds)
# enriched_df, summary_df, cluster_meta_df = wordcloud_guided_clustering(security_df, seeds, make_plots=False)

# 3) Columns you can use in the dashboard:
# enriched_df[["DESCRIPTION","security_seed","security_cluster_id","security_cluster_label","security_ml_noissue_proba"]].head()
# summary_df
# cluster_meta_df.head(20)
