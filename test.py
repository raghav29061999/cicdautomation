def print_clusters(df, cluster_col="cluster", label_col="cluster_label", issue_col="issue", max_examples=5):
    for cid in sorted(df[cluster_col].unique()):
        label = df[df[cluster_col] == cid][label_col].iloc[0]
        print(f"\n=== Cluster {cid} | Label: {label} ===")
        examples = df.loc[df[cluster_col] == cid, issue_col].head(max_examples)
        for ex in examples:
            print(f" - {ex}")

print_clusters(df5, cluster_col="cluster", label_col="cluster_label", issue_col="issue", max_examples=5)
