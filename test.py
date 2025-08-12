# ====================== imports ======================
import re, string, math
import numpy as np
import pandas as pd
from collections import defaultdict
from typing import List, Tuple, Dict

# Embeddings
from sentence_transformers import SentenceTransformer

# Optional: lemmatization (NLTK)
import nltk
from nltk.stem import WordNetLemmatizer
from nltk.corpus import wordnet
# Ensure wordnet is available
try:
    _ = wordnet.synsets('word')
except LookupError:
    nltk.download('wordnet')
    nltk.download('omw-1.4')

from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
from sklearn.preprocessing import normalize
from sklearn.metrics.pairwise import cosine_similarity

# ================== configurable rules ==================
DOMAIN_STOP = set(ENGLISH_STOP_WORDS) | {
    "potential","possibly","issue","issues","vulnerability","vulnerabilities",
    "found","detected","observed","present","may","might","could","risk","risks"
}

PHRASE_RULES = {
    r"\bsql injection\b|\bsqli\b|sql\s*(vuln|injection)": "sql_injection",
    r"(hard[-\s]?coded|hardcoded).*(key|token|secret|credential)s?": "hardcoded_keys",
    r"(api\s*key|access\s*key|secret\s*key|token|secret)s?.*(exposed|leaked|public|committed|pushed|in code)": "credentials_exposed",
    r"(password)s?.*(hardcoded|in code|exposed|plaintext)": "password_exposed",
    r"\b(open redirect|open redirection)\b": "open_redirect",
    r"(xss|cross[-\s]?site scripting)": "xss",
    r"(csrf|cross[-\s]?site request forgery)": "csrf",
    r"(ssrf|server[-\s]?side request forgery)": "ssrf",
    # Add any more you observe frequently:
    r"(missing|no)\s*rate[-\s]?limit(ing)?": "missing_rate_limiting",
    r"(weak|insecure)\s*(ssl|tls)|tls\s*1\.0|ssl\s*v[23]": "weak_tls_ssl",
    r"(open|public)\s*(s3|bucket)|bucket\s*policy\s*public": "open_storage_bucket",
}

COMPILED_RULES = [(re.compile(pat, re.I), tag) for pat, tag in PHRASE_RULES.items()]

TOKEN_MAP = {
    "sqli": "sql_injection", "xss":"xss", "csrf":"csrf","ssrf":"ssrf",
    "hard-code":"hardcoded", "hardcode":"hardcoded", "hard-coded":"hardcoded",
    "credential":"credentials","creds":"credentials",
    "token":"tokens","key":"keys","leak":"leaked","expose":"exposed",
}

PLACEHOLDERS = [
    (re.compile(r"https?://\S+", re.I), "<url>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<ip>"),
    (re.compile(r"[A-Za-z]:\\[^\s]+|/[^ \t\n\r\f\v]+"), "<path>"),
    (re.compile(r"[0-9a-f]{32,64}", re.I), "<hash>"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "<email>"),
    (re.compile(r"\b\d+\b"), "<num>"),
]

# ================== preprocessing ==================
_wnl = WordNetLemmatizer()

def _basic_clean(t: str) -> str:
    t = str(t).lower()
    for pat, repl in PLACEHOLDERS:
        t = pat.sub(repl, t)
    t = t.translate(str.maketrans("", "", string.punctuation))
    t = re.sub(r"\s+", " ", t).strip()
    return t

def _apply_phrase_rules(t: str) -> Tuple[str, set]:
    tags = set()
    for pat, tag in COMPILED_RULES:
        if pat.search(t):
            t = pat.sub(tag, t)
            tags.add(tag)
    return t, tags

def _lemmatize_token(w: str) -> str:
    # try verb then noun (cheap & robust)
    lem = _wnl.lemmatize(w, 'v')
    lem = _wnl.lemmatize(lem, 'n')
    return lem

def normalize_security_text(text: str, tag_boost:int=2) -> Tuple[str, List[str]]:
    """
    1) lowercase + placeholders
    2) phrase rules -> canonical tags (sql_injection, hardcoded_keys, ...)
    3) token-level normalization: synonym map + lemmatization
    4) drop domain stopwords, short tokens
    5) append detected tags (boost) to influence embeddings
    """
    t = _basic_clean(text)
    t, tags = _apply_phrase_rules(t)

    toks = []
    for w in t.split():
        w = TOKEN_MAP.get(w, w)
        w = _lemmatize_token(w)
        if len(w) > 2 and w not in DOMAIN_STOP:
            toks.append(w)

    if tags:
        for _ in range(max(0, tag_boost)):
            toks.extend(tags)

    return " ".join(toks), sorted(list(tags))

# ================== embeddings ==================
def embed_texts(texts: List[str], model_name="all-MiniLM-L6-v2") -> np.ndarray:
    model = SentenceTransformer(model_name)
    # L2-normalized embeddings help cosine-based thresholds
    return model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)

# ================== streaming (threshold) clustering ==================
class OnlineCosineClustering:
    """
    Assign each vector to the nearest centroid if cosine_sim >= threshold;
    otherwise start a new cluster. Centroids are updated (mean).
    Designed for batch + incremental.
    """
    def __init__(self, threshold: float = 0.78):
        self.threshold = threshold
        self.centroids: Dict[int, np.ndarray] = {}
        self.members: Dict[int, List[int]] = defaultdict(list)
        self._next_id = 0

    @staticmethod
    def _cos_sim(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.clip(np.dot(a, b) / (np.linalg.norm(a)*np.linalg.norm(b) + 1e-12), -1.0, 1.0))

    def _best_cluster(self, vec: np.ndarray) -> Tuple[int, float]:
        if not self.centroids:
            return -1, -1.0
        ids = list(self.centroids.keys())
        C = np.vstack([self.centroids[i] for i in ids])
        sims = cosine_similarity(vec.reshape(1,-1), C).ravel()
        j = int(np.argmax(sims))
        return ids[j], float(sims[j])

    def _update_centroid(self, cid: int, vecs: np.ndarray, indices: List[int]):
        # mean of member vectors
        self.centroids[cid] = vecs[indices].mean(axis=0)
        self.centroids[cid] /= (np.linalg.norm(self.centroids[cid]) + 1e-12)

    def fit_predict(self, X: np.ndarray) -> np.ndarray:
        labels = np.full(X.shape[0], -1, dtype=int)
        for i, v in enumerate(X):
            best_id, best_sim = self._best_cluster(v)
            if best_sim >= self.threshold:
                labels[i] = best_id
                self.members[best_id].append(i)
                self._update_centroid(best_id, X, self.members[best_id])
            else:
                cid = self._next_id
                self._next_id += 1
                self.centroids[cid] = v / (np.linalg.norm(v) + 1e-12)
                self.members[cid].append(i)
                labels[i] = cid
        return labels

    def partial_predict(self, X_new: np.ndarray) -> np.ndarray:
        """Assign incoming batch to existing clusters or new ones."""
        out = np.full(X_new.shape[0], -1, dtype=int)
        for i, v in enumerate(X_new):
            best_id, best_sim = self._best_cluster(v)
            if best_sim >= self.threshold:
                out[i] = best_id
                self.members[best_id].append(-(i+1))  # mark as new (optional)
                # Update centroid with new vec (EMA to be gentle)
                self.centroids[best_id] = normalize((self.centroids[best_id] + v).reshape(1,-1)).ravel()
            else:
                cid = self._next_id
                self._next_id += 1
                self.centroids[cid] = v / (np.linalg.norm(v) + 1e-12)
                out[i] = cid
        return out

# ================== merge clusters to exactly K ==================
def merge_to_k(centroids: Dict[int, np.ndarray], labels: np.ndarray, k_target: int = 5):
    """
    Merge clusters greedily by highest cosine similarity until number of clusters == k_target.
    Updates labels during merging so there are no stale IDs.
    """
    def cos(a, b):
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))

    cen = {cid: centroids[cid].copy() for cid in set(labels)}
    while len(cen) > k_target:
        cids = list(cen.keys())
        best = (-1, -1, -2.0)
        for i in range(len(cids)):
            for j in range(i + 1, len(cids)):
                s = cos(cen[cids[i]], cen[cids[j]])
                if s > best[2]:
                    best = (cids[i], cids[j], s)
        a, b, _ = best

        # Merge b into a
        labels[labels == b] = a
        # recompute centroid a
        a_vecs = [centroids[idx] for idx in labels if idx == a]  # This line needs actual vectors; we have cen[a] + cen[b]
        cen[a] = normalize((cen[a] + cen[b]).reshape(1, -1)).ravel()
        del cen[b]

    # Relabel to 0..k-1
    unique_ids = sorted(set(labels))
    remap = {cid: i for i, cid in enumerate(unique_ids)}
    new_labels = np.array([remap[c] for c in labels])
    new_centroids = {remap[cid]: vec for cid, vec in cen.items()}

    return new_labels, new_centroids

# ================== labeling with c-TF-IDF ==================
def ctfidf_labels(df: pd.DataFrame, text_col: str, cluster_col: str, top_n: int = 5) -> Dict[int, str]:
    grp = df.groupby(cluster_col)[text_col].apply(lambda s: " ".join(s)).reset_index()
    vec = TfidfVectorizer(ngram_range=(1,3), max_features=10000, stop_words=list(DOMAIN_STOP))
    X = normalize(vec.fit_transform(grp[text_col]), norm="l2", axis=1)
    vocab = np.array(vec.get_feature_names_out())
    out = {}
    for i, cid in enumerate(grp[cluster_col].tolist()):
        row = X[i].toarray().ravel()
        idx = row.argsort()[::-1][:top_n]
        out[cid] = " | ".join(vocab[idx])
    return out

# ================== main API ==================
def cluster_security_streaming_to_k(
    df: pd.DataFrame,
    issue_col: str = "issue",
    similarity_threshold: float = 0.80,
    k_target: int = 5,
    tag_boost: int = 3,
    model_name: str = "all-MiniLM-L6-v2",
):
    """
    - Strong preprocessing (placeholders + phrase rules + lemmatization + synonyms + tag boosting)
    - Online cosine clustering with threshold (assign to existing cluster if similar, else new)
    - Greedy centroid merges to force exactly k_target clusters
    - c-TF-IDF labeling
    Returns: df_out, labels_dict, centroids
    """
    if issue_col not in df.columns:
        raise ValueError(f"{issue_col} not in dataframe")

    # 1) Normalize text
    cleaned, tags = [], []
    for x in df[issue_col].astype(str).tolist():
        nx, tg = normalize_security_text(x, tag_boost=tag_boost)
        cleaned.append(nx); tags.append(tg)

    # 2) Embeddings
    emb = embed_texts(cleaned, model_name=model_name)

    # 3) Online clustering with cosine threshold
    online = OnlineCosineClustering(threshold=similarity_threshold)
    raw_labels = online.fit_predict(emb)  # raw cluster ids (variable count)

    # 4) Merge to exactly K clusters
    merged_labels, merged_centroids = merge_to_k(online.centroids, raw_labels, k_target=k_target)

    # 5) Build output + labels
    out = df.copy()
    out["normalized_issue"] = cleaned
    out["detected_tags"] = tags
    out["cluster"] = merged_labels

    name_map = ctfidf_labels(out, text_col="normalized_issue", cluster_col="cluster", top_n=6)
    out["cluster_label"] = out["cluster"].map(name_map)

    return out, name_map, merged_centroids
//////

# df: your dataframe with column 'issue'
df5, labels5, centroids = cluster_security_streaming_to_k(
    df,
    issue_col="issue",
    similarity_threshold=0.80,  # tighten/loosen as needed; try 0.78–0.85
    k_target=5,
    tag_boost=3,                # increase if SQL/hardcoded variants still split
    model_name="all-MiniLM-L6-v2"
)

print(df5['cluster'].value_counts().sort_index())
print(labels5)
