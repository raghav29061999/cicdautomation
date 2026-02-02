import re
from typing import List, Tuple, Optional


def _split_gherkin_files(raw: str) -> List[Tuple[str, str]]:
    """
    Robust splitter:
      1) If LLM uses markers: "### FILE: name.feature" -> split by markers.
      2) Else split by Scenario / Scenario Outline -> one file per scenario.
      3) Else fallback to a single file.

    NEVER returns [] if raw has non-whitespace content.
    """
    if raw is None:
        return []

    text = raw.strip()
    if not text:
        return []

    # ------------------------------------------------------------
    # 1) Marker-based splitting (if present)
    # ------------------------------------------------------------
    if "### FILE:" in text:
        files: List[Tuple[str, str]] = []
        lines = text.splitlines()

        cur_name: Optional[str] = None
        cur_buf: List[str] = []

        def flush():
            nonlocal cur_name, cur_buf
            if cur_name and any(l.strip() for l in cur_buf):
                body = "\n".join(cur_buf).strip() + "\n"
                name = cur_name if cur_name.endswith(".feature") else f"{cur_name}.feature"
                files.append((name, body))
            cur_name, cur_buf = None, []

        for ln in lines:
            if ln.strip().startswith("### FILE:"):
                flush()
                cur_name = ln.split("### FILE:", 1)[1].strip() or "feature"
                cur_buf = []
            else:
                if cur_name is not None:
                    cur_buf.append(ln)

        flush()

        # If markers existed but produced nothing, fallback
        if files:
            return files

    # ------------------------------------------------------------
    # 2) Scenario-based splitting (one scenario per file)
    # ------------------------------------------------------------
    # Keep original text but remove any leading junk lines before "Feature:"
    m = re.search(r"(?m)^\s*Feature:\s+.+$", text)
    if m:
        text = text[m.start():].strip()

    # Identify Feature header and optional Background block
    lines = [ln.rstrip() for ln in text.splitlines()]

    # If no scenario exists at all, fallback to single file
    has_scenario = any(re.match(r"^\s*(Scenario:|Scenario Outline:)\s+", ln) for ln in lines)
    if not has_scenario:
        return [("feature_001.feature", text.strip() + "\n")]

    # Capture feature lines up to Background/Scenario
    feature_block: List[str] = []
    background_block: List[str] = []
    scenarios: List[List[str]] = []

    i = 0
    # Feature + description block
    while i < len(lines):
        ln = lines[i]
        if re.match(r"^\s*Background:\s*", ln) or re.match(r"^\s*(Scenario:|Scenario Outline:)\s+", ln):
            break
        feature_block.append(ln)
        i += 1

    # Background block (optional)
    if i < len(lines) and re.match(r"^\s*Background:\s*", lines[i]):
        while i < len(lines):
            ln = lines[i]
            if re.match(r"^\s*(Scenario:|Scenario Outline:)\s+", ln):
                break
            background_block.append(ln)
            i += 1

    # Scenario blocks
    current: List[str] = []
    while i < len(lines):
        ln = lines[i]
        if re.match(r"^\s*(Scenario:|Scenario Outline:)\s+", ln):
            if current:
                scenarios.append(current)
            current = [ln]
        else:
            if current:
                current.append(ln)
        i += 1
    if current:
        scenarios.append(current)

    # Build one file per scenario
    out_files: List[Tuple[str, str]] = []
    for idx, sc_lines in enumerate(scenarios, start=1):
        body_lines: List[str] = []
        if any(l.strip() for l in feature_block):
            body_lines.extend(feature_block)
            body_lines.append("")
        if any(l.strip() for l in background_block):
            body_lines.extend(background_block)
            body_lines.append("")
        body_lines.extend(sc_lines)

        out_files.append((f"scenario_{idx:03d}.feature", "\n".join(body_lines).strip() + "\n"))

    # Safety fallback (should never be empty here)
    if not out_files:
        return [("feature_001.feature", text.strip() + "\n")]

    return out_files
