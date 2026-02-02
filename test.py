def _split_gherkin_files(raw: str) -> List[Tuple[str, str]]:
    """
    Split Gherkin text into one file per Scenario / Scenario Outline.
    Each output file will contain:
      - Feature header
      - Background (if present)
      - Exactly ONE Scenario
    """
    lines = [ln.rstrip() for ln in raw.splitlines() if ln.strip()]

    if not lines:
        return []

    feature_lines = []
    background_lines = []
    scenarios = []

    current_scenario = []
    in_background = False
    in_scenario = False

    for ln in lines:
        if ln.startswith("Feature:"):
            feature_lines = [ln]
            in_background = False
            in_scenario = False

        elif ln.startswith("Background:"):
            background_lines = [ln]
            in_background = True
            in_scenario = False

        elif ln.startswith(("Scenario:", "Scenario Outline:")):
            if current_scenario:
                scenarios.append(current_scenario)
            current_scenario = [ln]
            in_scenario = True
            in_background = False

        else:
            if in_scenario:
                current_scenario.append(ln)
            elif in_background:
                background_lines.append(ln)
            else:
                # feature-level description lines
                feature_lines.append(ln)

    if current_scenario:
        scenarios.append(current_scenario)

    files = []
    for idx, scenario_lines in enumerate(scenarios, start=1):
        filename = f"scenario_{idx:03d}.feature"

        content_lines = []
        content_lines.extend(feature_lines)
        content_lines.append("")  # spacer

        if background_lines:
            content_lines.extend(background_lines)
            content_lines.append("")

        content_lines.extend(scenario_lines)
        content = "\n".join(content_lines).strip() + "\n"

        files.append((filename, content))

    return files
