import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Optional, List, Dict, Iterable

# =========================
# Helpers
# =========================
def split_by_target(df: pd.DataFrame, target_col: str = "TARGET_ISSUE") -> Dict[str, pd.DataFrame]:
    """Return dict of slices keyed by unique TARGET_ISSUE values (uppercased)."""
    d = df.copy()
    d[target_col] = d[target_col].astype(str).str.strip().str.upper()
    return {k: d.loc[d[target_col] == k].copy() for k in d[target_col].unique()}

def _apply_filters(df: pd.DataFrame,
                   target: Optional[Iterable[str]] = None,
                   vertical: Optional[Iterable[str]] = None,
                   code_type: Optional[Iterable[str]] = None,
                   issues: Optional[Iterable[str]] = None,
                   target_col="TARGET_ISSUE",
                   vertical_col="Vertical",
                   code_col="code_Type",
                   issue_col="ISSUE_NAME") -> pd.DataFrame:
    """Filter df by optional lists (case-insensitive for TARGET_ISSUE)."""
    d = df.copy()
    if target is not None:
        tset = {str(x).strip().upper() for x in target}
        d[target_col] = d[target_col].astype(str).str.strip().str.upper()
        d = d[d[target_col].isin(tset)]
    if vertical is not None:
        d = d[d[vertical_col].isin(vertical)]
    if code_type is not None:
        d = d[d[code_col].isin(code_type)]
    if issues is not None:
        d = d[d[issue_col].isin(issues)]
    return d

def _severity_levels(df: pd.DataFrame, severity_col: str = "severity") -> List[str]:
    """Dynamic severity ordering by frequency (no assumptions)."""
    s = df[severity_col].astype(str).str.strip().replace({"": "NA"})
    return list(s.value_counts().index)

# =========================
# 1) ISSUE_NAME × severity (stacked bars)
# =========================
def plot_issue_severity_stacked(df: pd.DataFrame,
                                issue_col: str = "ISSUE_NAME",
                                severity_col: str = "severity",
                                *,
                                top_n_issues: int = 10,
                                normalize_within_issue: bool = False,
                                target: Optional[Iterable[str]] = None,
                                vertical: Optional[Iterable[str]] = None,
                                code_type: Optional[Iterable[str]] = None,
                                issues: Optional[Iterable[str]] = None,
                                title: Optional[str] = None):
    """
    Stacked bars of ISSUE_NAME split by severity (dynamic severity levels).
    Works great to see, e.g., 'In SECURITY, how many SQL Injections are High risk?'.
    Use 'target'=['SECURITY'] and 'issues'=['SQL Injections'] to zoom in.
    """
    d = _apply_filters(df, target, vertical, code_type, issues)
    if d.empty:
        print("No data after filters.")
        return

    sev_levels = _severity_levels(d, severity_col)
    top_issues = d[issue_col].value_counts().head(top_n_issues).index
    sub = d[d[issue_col].isin(top_issues)].copy()

    pivot = (sub.groupby([issue_col, severity_col]).size()
               .unstack(fill_value=0)
               .reindex(columns=sev_levels, fill_value=0))
    if normalize_within_issue:
        pivot = pivot.div(pivot.sum(axis=1), axis=0).fillna(0)

    ax = pivot.plot(kind="bar", stacked=True, figsize=(12, 6))
    ax.set_xlabel(issue_col); ax.set_ylabel("Share" if normalize_within_issue else "Count")
    ax.set_title(title or f"{issue_col} × {severity_col}")
    plt.xticks(rotation=30, ha="right"); plt.tight_layout(); plt.show()

# =========================
# 2) Top issues (overall or filtered)
# =========================
def plot_top_issues(df: pd.DataFrame,
                    issue_col: str = "ISSUE_NAME",
                    *,
                    top_n: int = 15,
                    normalize: bool = False,
                    target: Optional[Iterable[str]] = None,
                    vertical: Optional[Iterable[str]] = None,
                    code_type: Optional[Iterable[str]] = None,
                    title: Optional[str] = None):
    d = _apply_filters(df, target, vertical, code_type)
    if d.empty:
        print("No data after filters.")
        return
    counts = d[issue_col].value_counts(normalize=normalize).head(top_n).sort_values()
    plt.figure(figsize=(10, 6))
    counts.plot(kind="barh")
    plt.xlabel("Share" if normalize else "Count"); plt.ylabel(issue_col)
    plt.title(title or f"Top {top_n} issues")
    plt.tight_layout(); plt.show()

# =========================
# 3) ISSUE_NAME × Vertical (heatmap)
# =========================
def plot_issue_vs_vertical_heatmap(df: pd.DataFrame,
                                   issue_col: str = "ISSUE_NAME",
                                   vertical_col: str = "Vertical",
                                   *,
                                   top_issues: int = 12,
                                   top_verticals: int = 10,
                                   target: Optional[Iterable[str]] = None,
                                   code_type: Optional[Iterable[str]] = None,
                                   title: Optional[str] = None,
                                   annotate: bool = True):
    """
    Heatmap of counts for ISSUE_NAME vs Vertical. (Pure matplotlib; no seaborn.)
    """
    d = _apply_filters(df, target=target, code_type=code_type)
    if d.empty:
        print("No data after filters.")
        return
    issues = d[issue_col].value_counts().head(top_issues).index
    verticals = d[vertical_col].value_counts().head(top_verticals).index
    sub = d[d[issue_col].isin(issues) & d[vertical_col].isin(verticals)]
    if sub.empty:
        print("No overlap between selected issues and verticals.")
        return

    mat = (sub.groupby([issue_col, vertical_col]).size()
             .unstack(fill_value=0)
             .reindex(index=issues, columns=verticals, fill_value=0))
    data = mat.values

    fig, ax = plt.subplots(figsize=(1.2*len(verticals)+4, 0.4*len(issues)+3))
    im = ax.imshow(data, aspect="auto")
    ax.set_xticks(np.arange(len(verticals))); ax.set_xticklabels(verticals, rotation=45, ha="right")
    ax.set_yticks(np.arange(len(issues))); ax.set_yticklabels(issues)
    ax.set_xlabel(vertical_col); ax.set_ylabel(issue_col)
    ax.set_title(title or f"{issue_col} vs {vertical_col}")
    fig.colorbar(im, ax=ax)
    if annotate:
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                ax.text(j, i, str(int(data[i, j])), ha="center", va="center", fontsize=8)
    plt.tight_layout(); plt.show()

# =========================
# 4) ISSUE_NAME × code_Type (stacked bars)
# =========================
def plot_issue_code_type_stacked(df: pd.DataFrame,
                                 issue_col: str = "ISSUE_NAME",
                                 code_col: str = "code_Type",
                                 *,
                                 top_n_issues: int = 12,
                                 normalize_within_issue: bool = False,
                                 target: Optional[Iterable[str]] = None,
                                 vertical: Optional[Iterable[str]] = None,
                                 title: Optional[str] = None):
    d = _apply_filters(df, target=target, vertical=vertical)
    if d.empty:
        print("No data after filters.")
        return
    issues = d[issue_col].value_counts().head(top_n_issues).index
    sub = d[d[issue_col].isin(issues)].copy()
    pivot = (sub.groupby([issue_col, code_col]).size()
               .unstack(fill_value=0))
    if normalize_within_issue:
        pivot = pivot.div(pivot.sum(axis=1), axis=0).fillna(0)

    ax = pivot.plot(kind="bar", stacked=True, figsize=(12, 6))
    ax.set_xlabel(issue_col); ax.set_ylabel("Share" if normalize_within_issue else "Count")
    ax.set_title(title or f"{issue_col} × {code_col}")
    plt.xticks(rotation=30, ha="right"); plt.tight_layout(); plt.show()

# =========================
# 5) Severity distribution (dynamic)
# =========================
def plot_severity_distribution(df: pd.DataFrame,
                               severity_col: str = "severity",
                               *,
                               normalize: bool = False,
                               target: Optional[Iterable[str]] = None,
                               vertical: Optional[Iterable[str]] = None,
                               code_type: Optional[Iterable[str]] = None,
                               title: Optional[str] = None):
    """
    Simple bar for severity (dynamic levels, no assumptions).
    """
    d = _apply_filters(df, target, vertical, code_type)
    if d.empty:
        print("No data after filters.")
        return
    sev_counts = d[severity_col].astype(str).str.strip().replace({"": "NA"}).value_counts(normalize=normalize)
    plt.figure(figsize=(8, 5))
    sev_counts.plot(kind="bar")
    plt.ylabel("Share" if normalize else "Count"); plt.xlabel(severity_col)
    plt.title(title or "Severity distribution")
    plt.tight_layout(); plt.show()
