import json
import ast
import pandas as pd

# your existing dataframe: url_df
# your existing function: scrape_to_json(url) -> JSON-like (dict/list) or string

# Output lists
url1, url2, url3, url4, url5 = [], [], [], [], []
extracted_keys = []  # optional: if you want to keep the key per row

def _parse_dict_like(cell):
    """Parse a dict stored as a string (JSON or Python-literal style)."""
    if pd.isna(cell):
        return {}
    if isinstance(cell, dict):
        return cell
    s = str(cell).strip()
    # Try JSON first, then Python literal (e.g., single quotes)
    try:
        return json.loads(s)
    except Exception:
        try:
            return ast.literal_eval(s)
        except Exception:
            return {}

def _safe_to_str(x):
    """Convert scrape_to_json output to a string reliably."""
    if isinstance(x, str):
        return x
    try:
        return json.dumps(x, ensure_ascii=False)
    except Exception:
        return str(x)

# Process each row
for _, row in url_df.iterrows():
    d = _parse_dict_like(row["List_URLS"])
    if not d:
        extracted_keys.append(None)
        lists = [url1, url2, url3, url4, url5]
        for L in lists:
            L.append(None)
        continue

    # Take the first (and presumably only) key
    key = next(iter(d))
    extracted_keys.append(key)

    urls = d.get(key, [])
    # Normalize to length 5
    urls = list(urls)[:5] + [None] * (5 - len(urls))

    # Call your scraper for each url index
    out_lists = [url1, url2, url3, url4, url5]
    for i, L in enumerate(out_lists):
        u = urls[i]
        if not u:
            L.append(None)
            continue
        try:
            res = scrape_to_json(u)     # <-- your function
            L.append(_safe_to_str(res)) # ensure string
        except Exception:
            L.append(None)

# (Optional) attach back to the dataframe
url_df = url_df.copy()
url_df["List_Key"] = extracted_keys
url_df["url1"] = url1
url_df["url2"] = url2
url_df["url3"] = url3
url_df["url4"] = url4
url_df["url5"] = url5
