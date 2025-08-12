from sklearn.cluster import KMeans, AgglomerativeClustering
# (optional) from sklearn.decomposition import PCA

def cluster_fixed_k_kmeans(embeddings, k=5, random_state=42):
    km = KMeans(n_clusters=k, init="k-means++", n_init=20, max_iter=500, random_state=random_state)
    return km.fit_predict(embeddings)

def cluster_fixed_k_agglom(embeddings, k=5):
    ag = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average")
    return ag.fit_predict(embeddings)

def process_issues_fixed_k(df, k=5, method="kmeans"):
    df = preprocess_dataframe(df, 'issue')
    embedder = EmbeddingModel()
    emb = embedder.encode(df['cleaned'].tolist())
    X = emb  # or use PCA to 50D if you like

    if method == "kmeans":
        labels = cluster_fixed_k_kmeans(X, k=k)
    elif method == "agglomerative":
        labels = cluster_fixed_k_agglom(X, k=k)
    else:
        raise ValueError("method must be 'kmeans' or 'agglomerative'")

    df['cluster'] = labels
    df, cluster_labels = label_clusters(df, cluster_column='cluster', text_column='cleaned')
    return df, cluster_labels, emb
