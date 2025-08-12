import re, string
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans, AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
from sklearn.preprocessing import normalize
from sentence_transformers import SentenceTransformer

# ---------- Configurable rule registry ----------
RULES = {
    r"\bsql injection\b|\bsqli\b|sql\s*(vuln|injection)": "sql_injection",
    r"(hard[-\s]?coded|hardcoded).*(key|token|secret|credential)s?": "hardcoded_keys",
    r"(api\s*key|access\s*key|secret\s*key|token|secret)s?.*(exposed|leaked|public|committed|pushed|in code)": "credentials_exposed",
    r"(password)s?.*(hardcoded|in code|exposed|plaintext)": "password_exposed",
    r"\b(open redirect|open redirection)\b": "open_redirect",
    r"(xss|cross[-\s]?site scripting)": "xss",
    r"(csrf|cross[-\s]?site request forgery)": "csrf",
    r"(ssrf|server[-\s]?side request forgery)": "ssrf",
    # add more below anytime...
}

_COMPILED = [(re.compile(pat, re.I), tag) for pat, tag in RULES.items()]

def register_rules(new_rules: dict[str, str]):
    """new_rules: {regex: tag}"""
    global RULES, _COMPILED
    RULES.update(new_rules)
    _COMPILED = [(re.compile(pat, re.I), tag) for pat, tag in RULES.items()]

# Examples of adding 2–3 more types (you can change these to match your data)
register_rules({
    r"(missing|no)\s*rate[-\s]?limit(ing)?": "missing_rate_limiting",
    r"(weak|insecure)\s*(ssl|tls)|tls\s*1\.0|ssl\s*v[23]": "weak_tls_ssl",
    r"(open|public)\s*(s3|bucket)|bucket\s*policy\s*public": "open_storage_bucket",
})

# ---------- Cleaning & normalization ----------
_DOMAIN_STOP = set(ENGLISH_STOP_WORDS) | {
    "potential","possibly","issue","issues","vulnerability","vulnerabilities",
    "found","detected","observed","present","may","might","could",
}

_PLACEHOLDERS = [
    (re.compile(r"https?://\S+", re.I), "<url>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<ip>"),
    (re.compile(r"[A-Za-z]:\\[^\s]+|/[^ \t\n\r\f\v]+"), "<path>"),
    (re.compile(r"[0-9a-f]{32,64}", re.I), "<hash>"),
    (re.compile(r"\b\d+\b"), "<num>"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "<email>"),
]

def _basic_clean(t: str) -> str:
    t = str(t).lower()
    for pat, repl in _PLACEHOLDERS: t = pat.sub(repl, t)
    t = t.translate(str.maketrans("", "", string.punctuation))
    return re.sub(r"\s+", " ", t).strip()

def normalize_with_rules(text: str, boost=2):
    t = _basic_clean(text)
    tags = set()
    for pat, tag in _COMPILED:
        if pat.search(t):
            # collapse phrase to canonical tag to unify wording
            t = pat.sub(tag, t)
            tags.add(tag)
    # light token cleanup + domain stopwords
    toks = [w for w in t.split() if w not in _DOMAIN_STOP and len(w) > 2]
    # bias embeddings toward detected archetypes
    for _ in range(max(0, boost)):
        toks.extend(tags)
    return " ".join(toks), sorted(tags)

# ---------- Embeddings & fixed-k clustering ----------
def embed_texts(texts, model="all-MiniLM-L6-v2"):
    return SentenceTransformer(model).encode(texts, convert_to_numpy=True, normalize_embeddings=True)

def cluster_fixed_k(emb, k=5, method="kmeans", random_state=42):
    if method == "kmeans":
        from sklearn.cluster import KMeans
        return KMeans(n_clusters=k, init="k-means++", n_init=20, max_iter=500, random_state=random_state).fit_predict(emb)
    else:
        from sklearn.cluster import AgglomerativeClustering
        return AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average").fit_predict(emb)

# ---------- c-TF-IDF labeling ----------
def ctfidf_labels(df, text_col, cluster_col, top_n=5):
    grp = df.groupby(cluster_col)[text_col].apply(lambda s: " ".join(s)).reset_index()
    vec = TfidfVectorizer(ngram_range=(1,3), max_features=8000, stop_words=list(_DOMAIN_STOP))
    X = normalize(vec.fit_transform(grp[text_col]), norm="l2", axis=1)
    vocab = np.array(vec.get_feature_names_out())
    out = {}
    for i, cid in enumerate(grp[cluster_col].tolist()):
        row = X[i].toarray().ravel()
        idx = row.argsort()[::-1][:top_n]
        out[cid] = " | ".join(vocab[idx])
    return out

# ---------- Main API ----------
def cluster_security_k5(df: pd.DataFrame, issue_col="issue", method="kmeans", label_top_n=5, tag_boost=2):
    if issue_col not in df.columns:
        raise ValueError(f"{issue_col} not in dataframe")
    cleaned, tags = [], []
    for x in df[issue_col].astype(str).tolist():
        c, tg = normalize_with_rules(x, boost=tag_boost)
        cleaned.append(c); tags.append(tg)
    emb = embed_texts(cleaned)
    labels = cluster_fixed_k(emb, k=5, method=method)
    out = df.copy()
    out["normalized_issue"] = cleaned
    out["detected_tags"] = tags
    out["cluster"] = labels
    name_map = ctfidf_labels(out, "normalized_issue", "cluster", top_n=label_top_n)
    out["cluster_label"] = out["cluster"].map(name_map)
    return out, name_map, emb

# ---------- Optional: discover new archetypes to add as rules ----------
def discover_new_archetypes(df: pd.DataFrame, issue_col="issue", min_group_size=8):
    """
    Clusters only the rows that matched NO rule, and proposes top n-grams as candidates.
    """
    mask_no_rule = df["detected_tags"].apply(lambda t: len(t) == 0)
    if not mask_no_rule.any():
        return pd.DataFrame(columns=["size","example","suggested_terms"])
    sub = df.loc[mask_no_rule].copy()
    if sub.empty or sub.shape[0] < min_group_size:
        return pd.DataFrame(columns=["size","example","suggested_terms"])
    # quick mini-discovery with agglomerative k=3 (tweak if you want)
    emb = embed_texts(sub[issue_col].astype(str).tolist())
    lbl = cluster_fixed_k(emb, k=min(3, max(2, len(sub)//min_group_size)), method="agglomerative")
    sub["tmp_cluster"] = lbl
    # label mini-clusters with TF-IDF to propose patterns
    props = []
    for cid, g in sub.groupby("tmp_cluster"):
        vec = TfidfVectorizer(ngram_range=(1,3), stop_words=list(_DOMAIN_STOP))
        X = vec.fit_transform(g[issue_col].astype(str).tolist())
        vocab = np.array(vec.get_feature_names_out())
        row = normalize(X.sum(axis=0)).A.ravel()
        idx = row.argsort()[::-1][:5]
        props.append({
            "size": len(g),
            "example": g[issue_col].iloc[0],
            "suggested_terms": ", ".join(vocab[idx])
        })
    return pd.DataFrame(props).sort_values("size", ascending=False)
////


# 1) Run clustering with 5 topics
out, labels, emb = cluster_security_k5(df, issue_col="issue", method="kmeans")

# 2) See results
print(out['cluster'].value_counts().sort_index())
print(labels)

# 3) If clusters still mix, try agglomerative
# out, labels, emb = cluster_security_k5(df, issue_col="issue", method="agglomerative")

# 4) Discover new archetypes from unmatched rows → add to RULES
suggestions = discover_new_archetypes(out, issue_col="issue")
print(suggestions.head())
# Then convert a suggested phrase into a regex + tag via register_rules({...}) and rerun.
