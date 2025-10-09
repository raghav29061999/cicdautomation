import pandas as pd
import ast
import json

# ----- Replace this with your real scraper -----
def scraped_heading_to_json(url):
    # example: return some dict-like result from scraping
    return {"url": url, "title": f"Simulated title for {url}"}
# ------------------------------------------------

# Example main dataframe (replace with your df)
df = pd.DataFrame({
    "query": ["What will happen in future", "Other query"],
    "other_col": [1, 2]
})

# Example url_df where each cell is a stringified dict mapping queries -> [urls]
url_df = pd.DataFrame({
    "urls": [
        "{'What will happen in future': ['https://a.com','https://b.com','https://c.com','https://d.com','https://e.com']}",
        "{'Other query': ['https://x.com','https://y.com']}"
    ]
})
# If your url_df instead has a single row with the entire dict string,
# the code below will still find it.

# -------- Helper functions --------
def safe_parse(cell):
    """
    Parse a cell which may be:
      - a dict/list object already
      - a stringified Python literal for dict/list
      - a JSON string
    Returns the parsed object or None.
    """
    if pd.isna(cell):
        return None
    if isinstance(cell, (dict, list)):
        return cell
    if isinstance(cell, str):
        try:
            return ast.literal_eval(cell)
        except Exception:
            try:
                return json.loads(cell)
            except Exception:
                return None
    return None

def get_urls_for_query(query, url_df, urls_col='urls', query_col='query'):
    """
    Try to find a list of URLs for `query` inside url_df.
    Handles several shapes:
      - rows where urls cell is a dict string mapping multiple queries -> lists
      - rows where urls cell is directly a stringified list (and a separate query column exists)
      - one-row url_df containing an entire dict
    """
    # 1) If url_df has an explicit query column, try direct lookup
    if query_col in url_df.columns:
        matched = url_df[url_df[query_col] == query]
        if not matched.empty and urls_col in matched.columns:
            parsed = safe_parse(matched[urls_col].iloc[0])
            # if parsed is list => return it
            if isinstance(parsed, list):
                return parsed
            # if parsed is dict and contains the same query key:
            if isinstance(parsed, dict) and query in parsed:
                val = parsed[query]
                return list(val) if isinstance(val, (list, tuple)) else [val] if val is not None else []
    # 2) Otherwise scan all url_df rows: each cell might be a dict mapping many queries -> lists
    if urls_col in url_df.columns:
        for cell in url_df[urls_col].dropna().unique():
            parsed = safe_parse(cell)
            if isinstance(parsed, dict):
                if query in parsed:
                    val = parsed[query]
                    return list(val) if isinstance(val, (list, tuple)) else [val] if val is not None else []
            # if parsed is list and url_df has same-order mapping that's not detectable here -> skip
    # 3) not found
    return []

# -------- Main processing: attach url_1..url_5 to df --------
def scrape_and_attach(row, max_urls=5):
    q = row['query']
    urls = get_urls_for_query(q, url_df)
    # pad/truncate to exactly max_urls items
    urls = (urls + [None] * max_urls)[:max_urls]

    out = {}
    for i, u in enumerate(urls, start=1):
        col = f"url_{i}"
        if u:
            try:
                result = scraped_heading_to_json(u)
                # convert scraper output to JSON string; fallback to str() if not serializable
                try:
                    out[col] = json.dumps(result, ensure_ascii=False, default=str)
                except TypeError:
                    out[col] = str(result)
            except Exception as e:
                out[col] = f"SCRAPE_ERROR: {e}"
        else:
            out[col] = None
    return pd.Series(out)

# Apply and merge into df
url_cols_df = df.apply(scrape_and_attach, axis=1)
df = pd.concat([df, url_cols_df], axis=1)

print(df)
