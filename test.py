# --- extra imports ---
from sklearn.cluster import KMeans, AgglomerativeClustering
# (optional) from sklearn.decomposition import PCA

# --- fixed-k clustering methods ---
def cluster_fixed_k_kmeans(embeddings, k=5, random_state=42):
    km = KMeans(
        n_clusters=k,
        init="k-means++",
        n_init=20,       # more restarts for stability
        max_iter=500,
        random_state=random_state
    )
    return km.fit_predict(embeddings)

def cluster_fixed_k_agglom(embeddings, k=5):
    # cosine distance tends to work well for sentence embeddings
    ag = AgglomerativeClustering(
        n_clusters=k,
        metric="cosine",
        linkage="average"
    )
    return ag.fit_predict(embeddings)

# --- main: force exactly 5 clusters on your existing pipeline ---
def process_issues_fixed_k(df, k=5, method="kmeans"):
    # Step 1: Preprocess
    df = preprocess_dataframe(df, 'issue')

    # Step 2: Embed
    embedder = EmbeddingModel()
    emb = embedder.encode(df['cleaned'].tolist())  # shape: (n, d)

    # (optional) light reduction for denoising:
    # pca = PCA(n_components=min(50, emb.shape[1]))
    # X = pca.fit_transform(emb)
    X = emb

    # Step 3: Fixed-k clustering
    if method == "kmeans":
        labels = cluster_fixed_k_kmeans(X, k=k)
    elif method == "agglomerative":
        labels = cluster_fixed_k_agglom(X, k=k)
    else:
        raise ValueError("method must be 'kmeans' or 'agglomerative'")

    df['cluster'] = labels

    # Step 4: Simple labels for now (you can swap with c-TF-IDF later)
    df, cluster_labels = label_clusters(df, cluster_column='cluster', text_column='cleaned')

    return df, cluster_labels, emb
