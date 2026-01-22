def generate_gherkin(state: PipelineState) -> PipelineState:
    """
    Generate Gherkin feature files from TestCases + TestData.
    """
    run_id = state.run_id
    run_dir = state.run_dir

    cir = load_json(run_dir / "CanonicalUserStoryCIR.json")
    test_cases = load_json(run_dir / "TestCases.json")
    test_data = load_json(run_dir / "TestData.json")

    prompt = load_prompt("gherkin_generation.txt")

    generator = GherkinGenerator(llm=state.llm)

    files = generator.generate(
        prompt_text=prompt,
        cir=cir,
        test_cases=test_cases,
        test_data=test_data,
        control={
            "strategy": state.gherkin_strategy,
            "max_scenarios": state.max_gherkin_scenarios,
        },
    )

    write_gherkin_files(run_dir, files)

    state.gherkin_generated = True
    return state
----


from pathlib import Path


PROMPTS_DIR = Path(__file__).parent


def load_prompt(filename: str) -> str:
    """
    Load prompt text from src/prompts/.
    """
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")
