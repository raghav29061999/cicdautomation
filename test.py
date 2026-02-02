def node_write_gherkin(state: dict) -> dict:
    """
    Writes gherkin files to runtime/<run_id>/gherkin

    HARD GUARANTEE:
      - 1 Scenario / Scenario Outline per .feature file

    This enforces output structure even if upstream LLM output is one single file.
    """
    from pathlib import Path

    run_dir = _ensure_run_dir(state)
    files = _require(state, "gherkin_files")  # list[(filename, content)]

    out_dir = run_dir / "gherkin"
    out_dir.mkdir(parents=True, exist_ok=True)

    def split_one_scenario_per_file(gherkin_text: str) -> list[str]:
        """
        Split a single gherkin text block into multiple gherkin text blocks,
        each containing exactly one Scenario / Scenario Outline.
        Keeps Feature header and Background (if present) in every file.
        """
        lines = [ln.rstrip() for ln in gherkin_text.splitlines()]

        # Remove empty leading/trailing lines, but keep internal spacing minimal
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        if not lines:
            return []

        feature_lines: list[str] = []
        background_lines: list[str] = []
        scenarios: list[list[str]] = []

        current: list[str] = []
        in_background = False
        in_scenario = False

        for ln in lines:
            stripped = ln.strip()

            if stripped.startswith("### FILE:"):
                # Ignore file markers entirely for splitting purposes
                continue

            if stripped.startswith("Feature:"):
                feature_lines = [ln]
                in_background = False
                in_scenario = False
                continue

            if stripped.startswith("Background:"):
                background_lines = [ln]
                in_background = True
                in_scenario = False
                continue

            if stripped.startswith("Scenario:") or stripped.startswith("Scenario Outline:"):
                if current:
                    scenarios.append(current)
                current = [ln]
                in_scenario = True
                in_background = False
                continue

            # Regular line
            if in_scenario:
                current.append(ln)
            elif in_background:
                background_lines.append(ln)
            else:
                # Feature description lines
                if feature_lines:
                    feature_lines.append(ln)

        if current:
            scenarios.append(current)

        # If no scenarios found, return as-is (single file)
        if not scenarios:
            return ["\n".join(lines).strip() + "\n"]

        outputs: list[str] = []
        for scenario_lines in scenarios:
            out_lines: list[str] = []
            if feature_lines:
                out_lines.extend(feature_lines)
                out_lines.append("")
            if background_lines:
                out_lines.extend(background_lines)
                out_lines.append("")
            out_lines.extend(scenario_lines)

            outputs.append("\n".join(out_lines).strip() + "\n")

        return outputs

    written: list[str] = []
    scenario_counter = 1

    # Enforce split-at-write-time
    for _name, content in files:
        chunks = split_one_scenario_per_file(content)
        for chunk in chunks:
            fname = f"scenario_{scenario_counter:03d}.feature"
            p = out_dir / fname
            p.write_text(chunk, encoding="utf-8")
            written.append(str(p))
            scenario_counter += 1

    state["gherkin_dir"] = str(out_dir)
    return {"gherkin_dir": str(out_dir), "gherkin_written": written}
