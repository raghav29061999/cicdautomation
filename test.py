import json
import re
from collections import defaultdict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, NavigableString, Tag


def scrape_to_heading_json(url: str, timeout: int = 20) -> dict:
  
    # ---------- Helpers ----------
    def _clean_text(text: str) -> str:
        # normalize whitespace nicely
        return re.sub(r"\s+", " ", text).strip()

    def _tag_is_heading(tag: Tag) -> bool:
        return tag.name in {"h1", "h2", "h3", "h4", "h5", "h6"}

    def _heading_level(tag: Tag) -> int:
        # tag.name is 'h1'..'h6'
        return int(tag.name[1])

    def _element_to_markdown(el: Tag) -> str:
        """Convert a content element into simple Markdown-ish text."""
        # remove scripts/styles
        for bad in el.find_all(["script", "style", "noscript"]):
            bad.decompose()

        # convert links to [text](url)
        for a in el.find_all("a"):
            label = _clean_text(a.get_text(" ", strip=True))
            href = a.get("href")
            if href:
                a.replace_with(f"[{label}]({urljoin(url, href)})")
            else:
                a.replace_with(label)

        # handle images: show alt (or file name) and absolute URL
        for img in el.find_all("img"):
            alt = _clean_text(img.get("alt") or "")
            src = img.get("src")
            if src:
                abs_src = urljoin(url, src)
                if alt:
                    img.replace_with(f"![{alt}]({abs_src})")
                else:
                    img.replace_with(f"![image]({abs_src})")

        # Lists -> bullet lines
        if el.name in {"ul", "ol"}:
            items = []
            for li in el.find_all("li", recursive=False):
                txt = _clean_text(li.get_text(" ", strip=True))
                if txt:
                    items.append(f"- {txt}")
            return "\n".join(items)

        # Tables -> simple TSV-like block
        if el.name == "table":
            rows = []
            for tr in el.find_all("tr", recursive=False):
                cols = []
                cells = tr.find_all(["th", "td"], recursive=False)
                for c in cells:
                    cols.append(_clean_text(c.get_text(" ", strip=True)))
                if cols:
                    rows.append("\t".join(cols))
            return "\n".join(rows)

        # Code blocks
        if el.name in {"pre", "code"}:
            txt = el.get_text("\n", strip=True)
            if not txt:
                return ""
            # fence it (avoid nesting backticks issues)
            fenced = "```"
            return f"{fenced}\n{txt}\n{fenced}"

        # Everything else -> flattened text
        text = el.get_text(" ", strip=True)
        return _clean_text(text)

    def _append_content(node: dict, text: str) -> None:
        """Append text to node['content'] with a newline separator."""
        if not text:
            return
        if node["content"]:
            node["content"] += "\n" + text
        else:
            node["content"] = text

    # Create a node object
    def _new_node() -> dict:
        return {"content": "", "children": {}, "_dupe_counter": defaultdict(int)}

    # Add child node under parent with dedup keying
    def _add_child(parent: dict, heading_title: str) -> dict:
        title = heading_title or "Untitled"
        k = title
        if k in parent["children"]:
            parent["_dupe_counter"][title] += 1
            k = f"{title} ({parent['_dupe_counter'][title]+1})"
        else:
            parent["_dupe_counter"][title] = 0

        parent["children"][k] = _new_node()
        return k, parent["children"][k]

    # ---------- Fetch & Parse ----------
    resp = requests.get(url, timeout=timeout, headers={
        "User-Agent": "Mozilla/5.0 (compatible; HeadingScraper/1.0)"
    })
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove obvious noise nodes
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    title_text = _clean_text(soup.title.get_text()) if soup.title else ""

    # Work from body (fall back to soup if missing)
    body = soup.body or soup

    # Root model: sections = dict of H1 nodes
    root = _new_node()  # synthetic root (level 0)
    root_level = 0

    # Stack of (level, title_key, node_dict)
    # Start with root
    stack = [(root_level, "_root", root)]

    # Ensure preamble content (before any heading) is captured
    preamble_key, preamble_node = _add_child(root, "_preamble")

    # Iterate document order through (headings + content blocks)
    # We'll walk all tags and consider:
    # - Headings h1..h6: open a new section at that level
    # - Content-ish tags (p, ul/ol, pre, code, blockquote, table, img, div sections): append to current node
    content_tags = {
        "p", "ul", "ol", "pre", "code", "blockquote", "table", "img",
        "section", "article", "div", "span", "figure", "figcaption", "dl"
    }

    # Walk all descendants in body order, but only tag elements
    for el in body.descendants:
        if isinstance(el, NavigableString):
            continue
        if not isinstance(el, Tag):
            continue

        # If it's a heading, open a new node at that level
        if _tag_is_heading(el):
            level = _heading_level(el)
            text = _clean_text(el.get_text(" ", strip=True))

            # Climb up to parent where parent_level < level
            while stack and stack[-1][0] >= level:
                stack.pop()
            if not stack:
                stack = [(root_level, "_root", root)]

            parent_level, parent_key, parent_node = stack[-1]

            # Add new child to parent
            child_key, child_node = _add_child(parent_node, text)

            # Push to stack
            stack.append((level, child_key, child_node))

            # Continue to next element (we don't append the heading itself as content)
            continue

        # Otherwise, it's a content-ish block: append to current section (top of stack)
        if el.name in content_tags:
            # Compute text once per tag at its first encounter (avoid double-counting via descendants)
            # Only process if this tag is a 'top' content tag (i.e., its parent isn't also content)
            parent = el.parent
            if isinstance(parent, Tag) and parent.name in content_tags and not _tag_is_heading(parent):
                # Skip: parent will handle aggregating
                continue

            md = _element_to_markdown(el)
            if md:
                # Append to current node
                level, key, node = stack[-1]
                # If we are still in preamble (no headings yet) and top is root, send to preamble
                if key == "_root":
                    node_to_use = preamble_node
                else:
                    node_to_use = node
                _append_content(node_to_use, md)

    # If preamble has no content, remove it
    if not preamble_node["content"] and not preamble_node["children"]:
        del root["children"][preamble_key]

    # Build final "sections" from root children (i.e., H1s + optional _preamble)
    # Anything directly under root that isn't a real H1 (like '_preamble') is also included.
    sections = {}
    for k, v in root["children"].items():
        # Drop helper key from each node
        def strip_helper(node: dict) -> dict:
            return {
                "content": node["content"],
                "children": {ck: strip_helper(cv) for ck, cv in node["children"].items()}
            }
        sections[k] = strip_helper(v)

    return {
        "url": url,
        "title": title_text,
        "sections": sections
    }


# ---------------- Demo ----------------
if __name__ == "__main__":
    test_url = "https://www.example.com/"
    data = scrape_to_heading_json(test_url)
    print(json.dumps(data, indent=2, ensure_ascii=False))
