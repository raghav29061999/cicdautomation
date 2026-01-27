prompt_gherkin = _read_prompt_file(os.getenv("PROMPT_GHERKIN_PATH", "./src/prompts/gherkin_generation.txt"))

initial_state = {
    # existing...
    "prompt_gherkin": prompt_gherkin,

    # limiter: default 5; user can override; 0 = unlimited
    "gherkin_max_files": int(os.getenv("GHERKIN_MAX_FILES", "5")),
}



GHERKIN_MAX_FILES=5
# set 0 for unlimited
