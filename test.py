def _split_feature_into_scenarios(gherkin_text: str) -> List[GherkinFeatureFile]:
    """
    If LLM returns one Feature with many Scenarios, split into one file per Scenario.
    Each output file will include the same Feature header + Background (if present),
    then exactly one Scenario block.
    """
    text = gherkin_text.replace("\r\n", "\n").strip() + "\n"

    # Extract Feature header + optional Background block (prefix)
    feature_match = re.search(r"(?m)^\s*Feature\s*:\s*.+$", text)
    if not feature_match:
        raise GherkinGenerationError("No 'Feature:' found; cannot split scenarios.")

    # Find first Scenario
    scen_starts = [m.start() for m in re.finditer(r"(?m)^\s*Scenario\s*:\s*.+$", text)]
    if not scen_starts:
        # fallback: treat entire blob as one file
        return [GherkinFeatureFile(filename="feature_01.feature", content=text)]

    prefix = text[:scen_starts[0]].rstrip() + "\n\n"  # Feature + Background

    # Chop each scenario block
    out: List[GherkinFeatureFile] = []
    scen_starts.append(len(text))  # sentinel
    for i in range(len(scen_starts) - 1):
        block = text[scen_starts[i] : scen_starts[i + 1]].strip() + "\n"
        content = prefix + block
        out.append(GherkinFeatureFile(filename=f"feature_{i+1:02d}.feature", content=content))

    return out
--------------

files = _split_feature_into_scenarios(gherkin_text)

---------------

  Background:
    Given the user navigates to "https://www.amazon.com"
    And the system is in a clean initial state

-----

9) Data binding and placeholder resolution:
   - Each scenario MUST bind to exactly one concrete data record from TestData.json.
   - If TestData.json contains placeholder-style values (e.g., "cat-a", "type-1"),
     treat them as legitimate concrete values for that scenario.
   - Do NOT invent new values outside TestData.json.
   - If a required attribute is completely missing from TestData.json:
       - Use "TBD" in the step
       - Add a comment explaining which data field was missing.
   - Never output generic invented labels like "Brand X", "Sample Item", or "Random Value".
-------

- For each scenario:
  - Select exactly one dataset_id from TestData.json.
  - If data_slices are present, select exactly one slice_id.
  - Use the selected record’s fields to populate Given/When/Then steps.
- Mention selected dataset_id and slice_id ONLY in comments.
- Do NOT expose dataset_id or slice_id in step text.
