import pandas as pd
import ast
import json

# Example scraper (replace with your actual one)
def scraped_heading_to_json(url):
    # Simulate your scraping logic
    return {"title": f"Scraped heading for {url}"}

# Example url_df
url_df = pd.DataFrame({
    "List_URLS": [
        "{'What will happen in future': ['https://a1.com','https://a2.com','https://a3.com','https://a4.com','https://a5.com']}",
        "{'Another query': ['https://b1.com','https://b2.com','https://b3.com','https://b4.com','https://b5.com']}"
    ]
})

# Initialize 5 empty lists
url1, url2, url3, url4, url5 = [], [], [], [], []

# Iterate through each row of url_df
for _, row in url_df.iterrows():
    # Safely parse the stringified dict
    try:
        data = ast.literal_eval(row["List_URLS"])
    except Exception:
        data = {}

    # Extract the first (and only) value list (list of URLs)
    urls = list(data.values())[0] if data else []

    # Ensure exactly 5 items (pad with None)
    urls = (urls + [None] * 5)[:5]

    # Scrape each and convert to string
    scraped = []
    for u in urls:
        if u:
            try:
                res = scraped_heading_to_json(u)
                scraped.append(json.dumps(res, ensure_ascii=False))
            except Exception as e:
                scraped.append(f"ERROR: {e}")
        else:
            scraped.append(None)

    # Append each result to corresponding list
    url1.append(scraped[0])
    url2.append(scraped[1])
    url3.append(scraped[2])
    url4.append(scraped[3])
    url5.append(scraped[4])

# ✅ Now you have 5 lists:
# url1, url2, url3, url4, url5

print("url1:", url1)
print("url2:", url2)
print("url3:", url3)
print("url4:", url4)
print("url5:", url5)

