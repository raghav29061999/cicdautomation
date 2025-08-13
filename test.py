# ML-based security classifier: weak supervision -> train -> predict
# Requires: scikit-learn, pandas
import re
import numpy as np
import pandas as pd
from typing import List, Tuple, Pattern, Dict
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.metrics import classification_report

# ============ CONFIG ============
TEXT_COL = "Security_issue"     # change if your column name differs
LABEL_PREFIX = "security"       # output column name prefix
CLASS_NAMES = [
    "SQL Injection",
    "Hardcoded Secrets",
    "Sensitive Data in Logs",
    "Weak Crypto / Random",
    "Command Injection",
    "Path Traversal / File Access",
    "AuthN/AuthZ Weakness",
]
NO_ISSUES_CLASS = "No Issues"
UNCAT_CLASS = "Unclustered/Other"

# Thresholds
NO_ISSUES_PROBA_THRESHOLD = 0.50   # tune on validation
MULTILABEL_PROBA_THRESHOLD = 0.45  # tune per class if you like
MIN_SUPPORT_RATIO = 0.01           # collapse tiny buckets in summary
RANDOM_STATE = 42

# ============ TEXT NORMALIZATION ============
def normalize_text(s: str) -> str:
    if not isinstance(s, str) or not s.strip():
        return ""
    s = s.lower()
    s = re.sub(r"[\t\r\n]+", " ", s)
    s = re.sub(r"[“”\"\'\[\]\(\)<>]+", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s

# ============ WEAK LABELS (BOOTSTRAP) ============
def compile_union(patterns: List[str]) -> Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns), flags=re.IGNORECASE)

NO_ISSUE_RX = compile_union([
    r"\bno\s+issues?\b",
    r"\bno\s+security\s+issues?\b",
    r"\bno\s+vulnerabilit(?:y|ies)\b",
    r"\bclean\b|\bcompliant\b|\bnothing\s+significant\b|\blooks\s+good\b|\bnil\b",
])

CATEGORY_PATTERNS: Dict[str, Pattern] = {
    "SQL Injection": compile_union([
        r"\bsql\s*injection\b",
        r"\bun[-\s]?parameteri[sz]ed\b",
        r"\bstring\s+concatenation\b.*\b(sql|query)\b",
        r"\bcursor\.execute\([^)]*(%s|\+|format\()",
        r"\b(user|external)\s+input\b.*\b(query|sql)\b",
        r"\btainted\s+input\b.*\bquery\b",
        r"\braw\s+sql\b|\bdynamic\s+query\b",
        r"\b(?:select|update|delete|insert)\b.*\+\s*user",
    ]),
    "Hardcoded Secrets": compile_union([
        r"\bhardcod(?:ed|ing)\b.*\b(secret|key|token|password|credential|api)\b",
        r"\b(api[\s\-_]?key|access[\s\-_]?key|secret[\s\-_]?key|bearer\s+token|jwt\s+secret|password)\b",
        r"\bAKIA[A-Z0-9]{16}\b",
        r"-----BEGIN (?:RSA|PRIVATE) KEY-----",
        r"\bsk_[A-Za-z0-9]{20,}\b",
    ]),
    "Sensitive Data in Logs": compile_union([
        r"\blog(ging)?\b.*\b(pi+i|password|token|email|phone|ssn|aadhaar|passport)\b",
        r"\bpii\b",
        r"\bsensitive\s+data\b.*\bexpos(e|ure)\b",
    ]),
    "Weak Crypto / Random": compile_union([
        r"\b(md5|sha1)\b",
        r"\brandom\.(?:random|randint)\b.*\b(token|secret|password|key)\b",
        r"\bbase64\b.*\b(encrypt|encryption)\b",
        r"\bssl[_\s-]?verify\s*=\s*(false|0)\b",
    ]),
    "Command Injection": compile_union([
        r"\bos\.system\(",
        r"\bsubprocess\.(?:popen|call|run)\(.*shell\s*=\s*true",
        r"\b(eval|exec)\s*\(",
    ]),
    "Path Traversal / File Access": compile_union([
        r"\.\./",
        r"\bpath\s*traversal\b",
        r"\bopen\([^)]*(user|input)",
    ]),
    "AuthN/AuthZ Weakness": compile_union([
        r"\b(auth(?:entica|ori)zation?)\b.*\b(missing|weak|bypass|disabled)\b",
        r"\brole[-\s]?based\s+access\b.*\b(missing|not enforced)\b",
        r"\bjwt\b.*\bverify\b.*\b(false|0|disabled)\b",
        r"\ballow\s+all\b",
    ]),
}

def weak_label_row(text: str) -> Tuple[int, np.ndarray]:
    """
    Returns:
        no_issues_label: 1 if NO ISSUES, else 0
        y_multi: shape (len(CLASS_NAMES),) with 1/0 per class
    """
    t = normalize_text(text)
    if not t:
        return (0, np.zeros(len(CLASS_NAMES), dtype=int))

    if NO_ISSUE_RX.search(t):
        return (1, np.zeros(len(CLASS_NAMES), dtype=int))

    y = np.zeros(len(CLASS_NAMES), dtype=int)
    for i, cname in enumerate(CLASS_NAMES):
        if CATEGORY_PATTERNS[cname].search(t):
            y[i] = 1
    return (0, y)

def generate_pseudo_labels(df: pd.DataFrame, text_col: str) -> Tuple[np.ndarray, np.ndarray]:
    no_issues = []
    y_multi = []
    for txt in df[text_col].fillna("").tolist():
        ni, y = weak_label_row(txt)
        no_issues.append(ni)
        y_multi.append(y)
    return np.array(no_issues, dtype=int), np.vstack(y_multi)

# ============ TRAINING ============
def train_no_issues_model(texts: List[str], y_noissues: np.ndarray) -> Pipeline:
    """
    Binary classifier: NoIssues (1) vs HasIssues (0)
    """
    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(
            preprocessor=normalize_text,
            ngram_range=(1,3),
            min_df=2,
            max_features=200_000
        )),
        ("clf", LogisticRegression(
            solver="liblinear",
            class_weight="balanced",
            max_iter=2000,
            random_state=RANDOM_STATE
        ))
    ])
    pipe.fit(texts, y_noissues)
    return pipe

def train_multilabel_model(texts: List[str], Y_multi: np.ndarray) -> Pipeline:
    """
    Multi-label classifier over CLASS_NAMES (for rows with issues).
    """
    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(
            preprocessor=normalize_text,
            ngram_range=(1,3),
            min_df=2,
            max_features=200_000
        )),
        ("clf", OneVsRestClassifier(
            LogisticRegression(
                solver="saga",
                class_weight="balanced",
                max_iter=3000,
                random_state=RANDOM_STATE,
                n_jobs=None
            ),
            n_jobs=None
        ))
    ])
    pipe.fit(texts, Y_multi)
    return pipe

# ============ PREDICTION & ATTACH ============
def predict_security_classes(
    df: pd.DataFrame,
    text_col: str,
    no_issues_model: Pipeline,
    multilabel_model: Pipeline,
    p_no_issues: float = NO_ISSUES_PROBA_THRESHOLD,
    p_class: float = MULTILABEL_PROBA_THRESHOLD,
) -> pd.DataFrame:
    out = df.copy()
    texts = out[text_col].fillna("").tolist()

    # No-issues probabilities (class 1 = No Issues)
    p_no = no_issues_model.predict_proba(texts)[:, 1]

    # For rows predicted "has issues", get class probabilities
    has_issues_mask = p_no < p_no_issues
    probs = np.zeros((len(out), len(CLASS_NAMES)))
    if has_issues_mask.any():
        probs[has_issues_mask, :] = multilabel_model.predict_proba(
            [texts[i] for i in np.where(has_issues_mask)[0]]
        )

    # Build labels per row
    all_labels = []
    primary_labels = []
    for i in range(len(out)):
        if p_no[i] >= p_no_issues:
            all_labels.append([NO_ISSUES_CLASS])
            primary_labels.append(NO_ISSUES_CLASS)
            continue

        # Multi-label: pick all classes above threshold
        row_probs = probs[i]
        idx = np.where(row_probs >= p_class)[0]
        if len(idx) == 0:
            all_labels.append([UNCAT_CLASS])
            primary_labels.append(UNCAT_CLASS)
        else:
            labels = [CLASS_NAMES[j] for j in idx]
            # primary is highest-prob class
            top = CLASS_NAMES[int(np.argmax(row_probs))]
            primary_labels.append(top)
            all_labels.append(labels)

    out[f"{LABEL_PREFIX}_ml_all"] = all_labels
    out[f"{LABEL_PREFIX}_ml_primary"] = primary_labels
    out[f"{LABEL_PREFIX}_ml_noissue_proba"] = p_no
    return out

# ============ SUMMARY ============
def security_summary(df: pd.DataFrame, primary_col: str = f"{LABEL_PREFIX}_ml_primary") -> pd.DataFrame:
    total = len(df)
    summary = (
        df[primary_col]
        .value_counts(dropna=False)
        .rename_axis("category")
        .reset_index(name="count")
    )
    summary["percent"] = (summary["count"] / max(total, 1) * 100).round(2)

    # Collapse rare categories (except No Issues & Unclustered/Other)
    threshold = max(1, int(total * MIN_SUPPORT_RATIO))
    mask_rare = (
        (summary["category"] != NO_ISSUES_CLASS) &
        (summary["category"] != UNCAT_CLASS) &
        (summary["count"] < threshold)
    )
    rare_count = summary.loc[mask_rare, "count"].sum()
    rare_percent = summary.loc[mask_rare, "percent"].sum()

    if rare_count > 0:
        summary = summary.loc[~mask_rare].reset_index(drop=True)
        # Add/merge into Unclustered/Other
        if UNCAT_CLASS in summary["category"].values:
            idx = summary.index[summary["category"] == UNCAT_CLASS][0]
            summary.at[idx, "count"] += rare_count
            summary.at[idx, "percent"] = round(summary.at[idx, "percent"] + rare_percent, 2)
        else:
            summary = pd.concat([
                summary,
                pd.DataFrame([{"category": UNCAT_CLASS, "count": rare_count, "percent": round(rare_percent, 2)}])
            ], ignore_index=True)

    # Nice order for charts
    order = {name: i+1 for i, name in enumerate(CLASS_NAMES)}
    order[NO_ISSUES_CLASS] = 98
    order[UNCAT_CLASS] = 99
    summary["sort_key"] = summary["category"].map(order).fillna(50)
    return summary.sort_values(["sort_key", "category"]).drop(columns="sort_key").reset_index(drop=True)

# ============ FULL FLOW ============
def train_security_models(security_df: pd.DataFrame, text_col: str = TEXT_COL):
    """
    1) Build pseudo-labels from weak rules
    2) Train No-Issues binary model
    3) Train multi-label model on issue rows
    Returns: (no_issues_model, multilabel_model)
    """
    # Generate pseudo-labels
    y_noissues, Y_multi = generate_pseudo_labels(security_df, text_col)
    texts = security_df[text_col].fillna("").tolist()

    # Train No-Issues model
    X_tr, X_te, y_tr, y_te = train_test_split(texts, y_noissues, test_size=0.2, random_state=RANDOM_STATE, stratify=y_noissues)
    no_issues_model = train_no_issues_model(X_tr, y_tr)

    # Optional quick report on pseudo-labels
    y_pred = (no_issues_model.predict_proba(X_te)[:,1] >= NO_ISSUES_PROBA_THRESHOLD).astype(int)
    print("[No Issues] pseudo-label validation:\n", classification_report(y_te, y_pred, digits=3))

    # Train multi-label on rows with issues in pseudo-labels
    issue_idx = np.where(y_noissues == 0)[0]
    if len(issue_idx) == 0:
        raise ValueError("All rows look like 'No Issues' from weak labels—cannot train multi-label model.")
    ml_texts = [texts[i] for i in issue_idx]
    ml_Y = Y_multi[issue_idx]

    X_tr2, X_te2, Y_tr2, Y_te2 = train_test_split(ml_texts, ml_Y, test_size=0.2, random_state=RANDOM_STATE)
    multilabel_model = train_multilabel_model(X_tr2, Y_tr2)

    # Optional quick report (micro-averaged F1) using decision threshold
    Y_probs = multilabel_model.predict_proba(X_te2)
    Y_pred = (Y_probs >= MULTILABEL_PROBA_THRESHOLD).astype(int)
    print("[Multi-label] pseudo-label validation (micro):")
    # Manual micro metrics to avoid extra deps
    tp = (Y_pred & Y_te2).sum()
    fp = (Y_pred & (1 - Y_te2)).sum()
    fn = ((1 - Y_pred) & Y_te2).sum()
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    print(f"precision={precision:.3f}, recall={recall:.3f}, f1={f1:.3f}")

    return no_issues_model, multilabel_model

def run_security_pipeline(security_df: pd.DataFrame, text_col: str = TEXT_COL):
    """
    Trains using weak supervision, predicts labels, and returns:
      - enriched_df with predictions
      - summary_df for dashboard tiles
      - trained models (no_issues_model, multilabel_model)
    """
    no_issues_model, multilabel_model = train_security_models(security_df, text_col=text_col)
    enriched = predict_security_classes(
        df=security_df,
        text_col=text_col,
        no_issues_model=no_issues_model,
        multilabel_model=multilabel_model,
        p_no_issues=NO_ISSUES_PROBA_THRESHOLD,
        p_class=MULTILABEL_PROBA_THRESHOLD
    )
    # Primary for dashboard
    summary = security_summary(enriched, primary_col=f"{LABEL_PREFIX}_ml_primary")
    return enriched, summary, (no_issues_model, multilabel_model)

# ============ EXAMPLE USAGE ============
if __name__ == "__main__":
    # Demo toy data. Replace with your ~13k-row security_df
    security_df = pd.DataFrame({
        TEXT_COL: [
            "Possible SQL Injection via unparameterized query in cursor.execute(query + user_input)",
            "API key hardcoded in settings.py",
            "No security issues found.",
            "PII logged: email and tokens exposed in logs",
            "Uses md5 for hashing passwords",
            "subprocess.run(cmd, shell=True) can lead to command injection",
            "Path traversal via '../' detected",
            "JWT verify disabled; authorization bypass possible",
            "Unknown wording here with rare pattern"
        ]
    })

    enriched, summary, _models = run_security_pipeline(security_df, text_col=TEXT_COL)
    print(enriched[[TEXT_COL, "security_ml_primary", "security_ml_all", "security_ml_noissue_proba"]])
    print(summary)
