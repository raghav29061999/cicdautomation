# --- imports (self-contained) ---
import re, string
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans, AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
from sklearn.preprocessing import normalize
from sentence_transformers import SentenceTransformer

# ---------- helpers ----------
def _preprocess_text(t: str) -> str:
    t = str(t).lower()
    t = re.sub(r'\d+', ' ', t)
    t = t.translate(str.maketrans('', '', string.punctuation))
    words = [w for w in t.split() if w not in ENGLISH_STOP_WORDS and len(w) > 2]
    return ' '.join(words)

def _embed_texts(texts, model_name='all-MiniLM-L6-v2'):
    model = SentenceTransformer(model_name)
    # normalized embeddings help clustering stability
    emb = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return emb

def _cluster_fixed_k(X: np.ndarray, k=5, method='kmeans', random_state=42):
    if method == 'kmeans':
        km = KMeans(n_clusters=k, init='k-means++', n_init=20, max_iter=500, random_state=random_state)
        return km.fit_predict(X)
    elif method == 'agglomerative':
        # average-link with cosine tends to work well for sentence embeddings
        ag = AgglomerativeClustering(n_clusters=k, metric='cosine', linkage='average')
        return ag.fit_predict(X)
    else:
        raise ValueError("method must be 'kmeans' or 'agglomerative'")

def _ctfidf_labels(df: pd.DataFrame, text_col: str, cluster_col: str, top_n=4):
    """
    Class-based TF-IDF over concatenated docs per cluster → better topic labels.
    """
    # build one "document" per cluster
    grouped = df.groupby(cluster_col)[text_col].apply(lambda s: ' '.join(s)).reset_index()
    clusters = grouped[cluster_col].tolist()
    docs = grouped[text_col].tolist()

    vec = TfidfVectorizer(ngram_range=(1,3), max_features=6000, stop_words='english')
    X = vec.fit_transform(docs)                   # shape: n_clusters x vocab
    X = normalize(X, norm='l2', axis=1)           # highlight salient terms per cluster
    vocab = np.array(vec.get_feature_names_out())

    labels = {}
    for i, cid in enumerate(clusters):
        row = X[i].toarray().ravel()
        idx = row.argsort()[::-1][:top_n]
        labels[cid] = ' | '.join(vocab[idx])
    return labels

# ---------- main API ----------
def cluster_to_five_topics(df: pd.DataFrame, issue_col='issue', method='kmeans', label_top_n=4):
    """
    From-scratch pipeline:
    - cleans text (no reliance on df['cleaned'])
    - sentence embeddings
    - fixed-k clustering (k=5)
    - c-TF-IDF labeling
    Returns: df_out (original + cluster + cluster_label), labels_dict, embeddings
    """
    if issue_col not in df.columns:
        raise ValueError(f"Column '{issue_col}' not found in dataframe.")

    # 1) Clean (kept internal; original df untouched)
    texts = df[issue_col].astype(str).apply(_preprocess_text).tolist()

    # 2) Embed
    emb = _embed_texts(texts)  # shape: (n_samples, d)

    # 3) Cluster (exactly 5)
    labels = _cluster_fixed_k(emb, k=5, method=method)

    # 4) Build labeled output dataframe
    out = df.copy()
    out['cluster'] = labels

    # 5) c-TF-IDF labels for meaning
    # Use the cleaned texts for labeling quality
    tmp = out[[issue_col]].copy()
    tmp['_cleaned_'] = texts
    tmp['cluster'] = labels
    label_map = _ctfidf_labels(tmp, text_col='_cleaned_', cluster_col='cluster', top_n=label_top_n)

    out['cluster_label'] = out['cluster'].map(label_map)

    return out, label_map, emb




/////////////////////

# df is your dataframe with a column 'issue'
df5, labels5, emb = cluster_to_five_topics(df, issue_col='issue', method='kmeans')  # or method='agglomerative'

print(df5['cluster'].value_counts().sort_index())
print(labels5)  # cluster -> label

# peek examples per cluster
for c in sorted(df5['cluster'].unique()):
    print(f"\n=== Cluster {c} | {labels5[c]} ===")
    print(df5.loc[df5['cluster']==c, 'issue'].head(5).to_string(index=False))
